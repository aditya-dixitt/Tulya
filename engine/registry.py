"""The national code registry: who has been issued what, and what happened since.

A code generator is not a registry. The generator (engine/codegen.py) answers
"what does the code for class X serial N look like"; this answers the three
questions a CPSE, an auditor and a purchase officer actually ask:

    given this legacy code, what is its national code?
    given this national code, what does it mean and who else uses it?
    this code used to work and now points somewhere else - why?

Three rules are enforced here rather than left to callers.

**Issuance is idempotent.**  Minting for a group whose members already carry a
code returns that code. Re-running the whole ERP load must not churn the
catalogue.

**Codes are never deleted, only superseded.**  When two already-coded items
are found to be the same item, the earlier code survives and the later one is
marked SUPERSEDED with a pointer to the survivor. The retired code still
resolves - forever - because it is printed on drawings, indents and warranty
claims that nobody is going to reissue. A registry that deletes codes breaks
history.

**A code is refused on incomplete evidence.**  If any of the class's defining
specifications could not be read, no code is issued and the reason is
recorded. This is the coverage floor from engine/score.py applied one stage
later: the engine declines to auto-merge on thin evidence, and the registry
declines to stamp a permanent national identifier on it. A wrong merge can be
un-merged; a wrong code is on a purchase order.
"""
import json
import time

from engine import codegen, taxonomy

SCHEMA = """
CREATE TABLE IF NOT EXISTS nmc_registry (
    nmc           TEXT PRIMARY KEY,
    class_code    TEXT NOT NULL,
    serial        INTEGER NOT NULL,
    signature     TEXT NOT NULL,
    description   TEXT NOT NULL,
    uom           TEXT,
    status        TEXT NOT NULL CHECK(status IN ('ACTIVE','SUPERSEDED')),
    superseded_by TEXT,
    issued_ts     REAL NOT NULL,
    issued_by     TEXT NOT NULL,
    UNIQUE (class_code, serial)
);
CREATE TABLE IF NOT EXISTS nmc_members (
    record_id    INTEGER PRIMARY KEY,
    nmc          TEXT NOT NULL,
    cpse         TEXT,
    plant        TEXT,
    legacy_code  TEXT,
    link_status  TEXT NOT NULL DEFAULT 'CONFIRMED'
                 CHECK(link_status IN ('CONFIRMED','PROVISIONAL')),
    corroborated INTEGER NOT NULL DEFAULT 0,
    unknown_keys TEXT,
    linked_ts    REAL NOT NULL,
    linked_by    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_members_nmc ON nmc_members (nmc);
CREATE TABLE IF NOT EXISTS nmc_events (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     REAL NOT NULL,
    event  TEXT NOT NULL,
    nmc    TEXT,
    actor  TEXT,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS nmc_refusals (
    group_key TEXT PRIMARY KEY,
    ts        REAL NOT NULL,
    reason    TEXT NOT NULL,
    detail    TEXT
);
"""


def init_registry(conn):
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _event(conn, event, nmc, actor, detail=""):
    conn.execute("INSERT INTO nmc_events (ts, event, nmc, actor, detail) VALUES (?,?,?,?,?)",
                 (time.time(), event, nmc, actor, detail))


def next_serial(conn, class_code):
    """Serials are per class, so two CPSEs onboarding different classes never
    contend for the same number and neither needs to wait on the other."""
    row = conn.execute("SELECT MAX(serial) FROM nmc_registry WHERE class_code=?",
                       (class_code,)).fetchone()
    return (row[0] or 0) + 1


def resolve(conn, nmc):
    """Follow a supersede chain to the code that is live today.

    Returns (live_nmc, hops). A retired code resolving in one hop is the normal
    case; more than one means it was merged twice, which is legal and must not
    loop - the chain is walked with a visited set.
    """
    seen, cur, hops = set(), str(nmc).upper(), 0
    while cur and cur not in seen:
        seen.add(cur)
        row = conn.execute("SELECT status, superseded_by FROM nmc_registry WHERE nmc=?",
                           (cur,)).fetchone()
        if not row:
            return None, hops
        if row[0] == "ACTIVE" or not row[1]:
            return cur, hops
        cur, hops = row[1], hops + 1
    return cur, hops


def get(conn, nmc):
    row = conn.execute(
        "SELECT nmc, class_code, serial, signature, description, uom, status, "
        "superseded_by, issued_ts, issued_by FROM nmc_registry WHERE nmc=?",
        (str(nmc).upper(),)).fetchone()
    if not row:
        return None
    d = dict(zip(["nmc", "class_code", "serial", "signature", "description", "uom",
                  "status", "superseded_by", "issued_ts", "issued_by"], row))
    d.update(taxonomy.describe(d["class_code"]))
    d["members"] = members_of(conn, d["nmc"])
    return d


def members_of(conn, nmc):
    rows = conn.execute(
        "SELECT record_id, cpse, plant, legacy_code, link_status, corroborated,"
        " unknown_keys, linked_ts FROM nmc_members WHERE nmc=? ORDER BY record_id",
        (str(nmc).upper(),)).fetchall()
    return [dict(record_id=r[0], cpse=r[1], plant=r[2], legacy_code=r[3],
                 link_status=r[4], corroborated=r[5],
                 unknown_keys=[k for k in (r[6] or "").split(",") if k], linked_ts=r[7])
            for r in rows]


def provisional_queue(conn, limit=500):
    """Rows carrying a national code that their own description cannot fully
    confirm. This is the work list a CPSE's material cell actually works
    through - each one needs a drawing, a spec sheet or a physical check."""
    rows = conn.execute(
        "SELECT m.record_id, m.nmc, m.cpse, m.plant, m.legacy_code, m.corroborated,"
        " m.unknown_keys, r.description, r.class_code FROM nmc_members m"
        " JOIN nmc_registry r ON r.nmc = m.nmc"
        " WHERE m.link_status='PROVISIONAL' ORDER BY m.corroborated, m.record_id LIMIT ?",
        (limit,)).fetchall()
    return [dict(record_id=r[0], nmc=r[1], cpse=r[2], plant=r[3], legacy_code=r[4],
                 corroborated=r[5],
                 unknown_keys=[k for k in (r[6] or "").split(",") if k],
                 code_description=r[7], class_code=r[8],
                 class_name=taxonomy.describe(r[8])["class_name"]) for r in rows]


def confirm_member(conn, record_id, actor, note=""):
    """A human has checked the row against the drawing. Promote it."""
    row = conn.execute("SELECT nmc FROM nmc_members WHERE record_id=?",
                       (int(record_id),)).fetchone()
    if not row:
        return None
    conn.execute("UPDATE nmc_members SET link_status='CONFIRMED', linked_by=?, linked_ts=?"
                 " WHERE record_id=?", (actor, time.time(), int(record_id)))
    _event(conn, "confirmed", row[0], actor, note or f"record {record_id} confirmed by hand")
    conn.commit()
    return row[0]


def code_for_record(conn, record_id):
    row = conn.execute("SELECT nmc FROM nmc_members WHERE record_id=?",
                       (int(record_id),)).fetchone()
    return row[0] if row else None


def code_for_legacy(conn, cpse, legacy_code):
    """The lookup a purchase officer does: their own code in, national code out."""
    row = conn.execute(
        "SELECT nmc FROM nmc_members WHERE cpse=? AND legacy_code=?",
        (cpse, str(legacy_code))).fetchone()
    if not row:
        return None
    live, _ = resolve(conn, row[0])
    return live


def _member_payload(rid, recs):
    r = recs.loc[int(rid)]
    return (int(rid), r.get("cpse", ""), r.get("plant", ""), str(r.get("legacy_code", "")))


def mint_for_group(conn, member_ids, recs, prep, actor="system", canonical_id=None):
    """Issue, reuse or consolidate the national code for one approved group.

    Returns a dict with `status` one of:
        issued      a new code was created
        reused      every member already sat under one code
        consolidated  members carried different codes; the oldest survived
        refused     the class's defining specs are not fully readable
    """
    member_ids = [int(m) for m in member_ids]
    if not member_ids:
        return dict(status="refused", reason="empty group", nmc=None)
    canonical_id = int(canonical_id if canonical_id is not None else member_ids[0])

    norm = prep.at[canonical_id, "norm"] if canonical_id in prep.index else ""
    try:
        attrs = json.loads(prep.at[canonical_id, "attrs"]) if canonical_id in prep.index else {}
    except Exception:
        attrs = {}
    info = taxonomy.classify(str(norm), attrs)
    class_code = info["class_code"]

    if class_code == taxonomy.UNCLASSIFIED:
        return _refuse(conn, member_ids, "unclassified",
                       "the item's class could not be read from its description")
    if not taxonomy.signature_is_complete(class_code, attrs):
        missing = [k for k in taxonomy.DEFINING_KEYS[class_code] if k not in attrs]
        return _refuse(conn, member_ids, "incomplete specification",
                       "defining specification(s) not readable: " + ", ".join(missing))

    signature = taxonomy.spec_signature(class_code, attrs)

    # what do the members already carry?
    existing = []
    for rid in member_ids:
        code = code_for_record(conn, rid)
        if code:
            live, _ = resolve(conn, code)
            if live:
                existing.append(live)
    existing = sorted(set(existing),
                      key=lambda c: conn.execute(
                          "SELECT issued_ts FROM nmc_registry WHERE nmc=?", (c,)).fetchone()[0])

    if not existing:
        serial = next_serial(conn, class_code)
        nmc = codegen.mint_code(class_code, serial)
        desc = str(recs.at[canonical_id, "description"])
        uom = str(recs.at[canonical_id, "uom"]) if "uom" in recs.columns else ""
        conn.execute(
            "INSERT INTO nmc_registry (nmc, class_code, serial, signature, description, uom,"
            " status, superseded_by, issued_ts, issued_by) VALUES (?,?,?,?,?,?, 'ACTIVE', NULL, ?, ?)",
            (nmc, class_code, serial, signature, desc, uom, time.time(), actor))
        _event(conn, "issued", nmc, actor, f"{info['class_name']} | {signature}")
        status = "issued"
    else:
        nmc = existing[0]
        status = "reused"
        for retired in existing[1:]:
            conn.execute("UPDATE nmc_registry SET status='SUPERSEDED', superseded_by=? WHERE nmc=?",
                         (nmc, retired))
            conn.execute("UPDATE nmc_members SET nmc=?, linked_ts=?, linked_by=? WHERE nmc=?",
                         (nmc, time.time(), actor, retired))
            _event(conn, "superseded", retired, actor, f"absorbed into {nmc}")
            status = "consolidated"

    # Each member earns its own link. Being in the group proves it does not
    # contradict the code; it does not prove the member supports it.
    linked = confirmed = provisional = 0
    held = []
    for rid in member_ids:
        payload = _member_payload(rid, recs)
        try:
            m_attrs = json.loads(prep.at[int(rid), "attrs"]) if int(rid) in prep.index else {}
        except Exception:
            m_attrs = {}
        verdict = taxonomy.signature_match(class_code, m_attrs, signature)
        if verdict["status"] in ("conflict", "unsupported"):
            held.append(dict(record_id=int(rid), legacy_code=payload[3],
                             reason=verdict["status"], matched=verdict["matched"],
                             unknown=verdict["unknown"], conflicting=verdict["conflicting"]))
            continue
        link_status = "CONFIRMED" if verdict["status"] == "confirmed" else "PROVISIONAL"
        confirmed += link_status == "CONFIRMED"
        provisional += link_status == "PROVISIONAL"
        cur = conn.execute("SELECT nmc, link_status FROM nmc_members WHERE record_id=?",
                           (payload[0],)).fetchone()
        if cur and cur[0] == nmc and cur[1] == link_status:
            continue
        conn.execute(
            "INSERT INTO nmc_members (record_id, nmc, cpse, plant, legacy_code, link_status,"
            " corroborated, unknown_keys, linked_ts, linked_by)"
            " VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(record_id) DO UPDATE SET"
            " nmc=excluded.nmc, link_status=excluded.link_status,"
            " corroborated=excluded.corroborated, unknown_keys=excluded.unknown_keys,"
            " linked_ts=excluded.linked_ts, linked_by=excluded.linked_by",
            (payload[0], nmc, payload[1], payload[2], payload[3], link_status,
             verdict["n_matched"], ",".join(verdict["unknown"]), time.time(), actor))
        linked += 1
    if linked:
        _event(conn, "linked", nmc, actor,
               f"{linked} legacy code(s) mapped ({confirmed} confirmed, "
               f"{provisional} provisional)")
    if held:
        _event(conn, "held", nmc, actor,
               f"{len(held)} member(s) not linked: " +
               ", ".join(f"{h['legacy_code']}({h['reason']})" for h in held[:5]))
    conn.execute("DELETE FROM nmc_refusals WHERE group_key=?", (_group_key(member_ids),))
    conn.commit()
    return dict(status=status, nmc=nmc, class_code=class_code, class_name=info["class_name"],
                signature=signature, linked=linked, members=len(member_ids),
                confirmed=confirmed, provisional=provisional, held=held,
                superseded=existing[1:] if len(existing) > 1 else [])


def _group_key(member_ids):
    return ",".join(str(i) for i in sorted(int(m) for m in member_ids))


def _refuse(conn, member_ids, reason, detail):
    conn.execute(
        "INSERT INTO nmc_refusals (group_key, ts, reason, detail) VALUES (?,?,?,?)"
        " ON CONFLICT(group_key) DO UPDATE SET ts=excluded.ts, reason=excluded.reason,"
        " detail=excluded.detail",
        (_group_key(member_ids), time.time(), reason, detail))
    conn.commit()
    return dict(status="refused", reason=reason, detail=detail, nmc=None,
                members=len(member_ids))


def unlink_record(conn, record_id, actor="system", note=""):
    """Un-merge: a record split out of its group loses its claim on that code.

    The code itself is untouched - the other members still use it, and even if
    they didn't, a code that has been issued is never withdrawn. The record
    becomes uncoded and will be minted again next time it is grouped.
    """
    record_id = int(record_id)
    row = conn.execute("SELECT nmc FROM nmc_members WHERE record_id=?", (record_id,)).fetchone()
    if not row:
        return None
    conn.execute("DELETE FROM nmc_members WHERE record_id=?", (record_id,))
    _event(conn, "unlinked", row[0], actor, note or f"record {record_id} split out")
    conn.commit()
    return row[0]


def catalogue(conn, status="ACTIVE"):
    """The national catalogue: one row per code, with everything mapped to it.

    This is the file a CPSE actually receives at the end of the exercise.
    """
    q = ("SELECT nmc, class_code, serial, signature, description, uom, status,"
         " superseded_by, issued_ts FROM nmc_registry")
    args = ()
    if status:
        q += " WHERE status=?"
        args = (status,)
    q += " ORDER BY class_code, serial"
    out = []
    for r in conn.execute(q, args):
        d = dict(zip(["nmc", "class_code", "serial", "signature", "description", "uom",
                      "status", "superseded_by", "issued_ts"], r))
        info = taxonomy.describe(d["class_code"])
        d.update(segment_name=info["segment_name"], family_name=info["family_name"],
                 class_name=info["class_name"], unspsc=info["unspsc"])
        d["members"] = members_of(conn, d["nmc"])
        d["cpses"] = sorted({m["cpse"] for m in d["members"] if m["cpse"]})
        d["plants"] = sorted({m["plant"] for m in d["members"] if m["plant"]})
        out.append(d)
    return out


def events(conn, limit=200):
    rows = conn.execute(
        "SELECT id, ts, event, nmc, actor, detail FROM nmc_events ORDER BY id DESC LIMIT ?",
        (limit,)).fetchall()
    return [dict(id=r[0], ts=r[1], event=r[2], nmc=r[3], actor=r[4], detail=r[5]) for r in rows]


def refusals(conn, limit=200):
    rows = conn.execute(
        "SELECT group_key, ts, reason, detail FROM nmc_refusals ORDER BY ts DESC LIMIT ?",
        (limit,)).fetchall()
    return [dict(group_key=r[0], ts=r[1], reason=r[2], detail=r[3]) for r in rows]


def stats(conn):
    active = conn.execute("SELECT COUNT(*) FROM nmc_registry WHERE status='ACTIVE'").fetchone()[0]
    superseded = conn.execute(
        "SELECT COUNT(*) FROM nmc_registry WHERE status='SUPERSEDED'").fetchone()[0]
    mapped = conn.execute("SELECT COUNT(*) FROM nmc_members").fetchone()[0]
    confirmed = conn.execute(
        "SELECT COUNT(*) FROM nmc_members WHERE link_status='CONFIRMED'").fetchone()[0]
    provisional = conn.execute(
        "SELECT COUNT(*) FROM nmc_members WHERE link_status='PROVISIONAL'").fetchone()[0]
    refused = conn.execute("SELECT COUNT(*) FROM nmc_refusals").fetchone()[0]
    by_class = [dict(class_code=r[0], class_name=taxonomy.describe(r[0])["class_name"], codes=r[1])
                for r in conn.execute(
                    "SELECT class_code, COUNT(*) FROM nmc_registry WHERE status='ACTIVE'"
                    " GROUP BY class_code ORDER BY COUNT(*) DESC")]
    return dict(active_codes=active, superseded_codes=superseded, legacy_codes_mapped=mapped,
                confirmed_links=confirmed, provisional_links=provisional,
                refused_groups=refused, by_class=by_class)
