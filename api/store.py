"""Persistence for steward decisions: reviews (approve/reject) and the audit trail.

SQLite via stdlib only — no Postgres client is installable in this sandbox
(PyPI is blocked, same constraint documented for the matching engine). The
schema is deliberately Postgres-shaped (explicit columns, no pickled blobs)
so swapping the connection layer for `psycopg2` later is a rewrite of this
one file, not of anything that calls it.
"""
import sqlite3
import time
import pathlib

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "out" / "steward.db"


def _key(a, b):
    """Pairs are unordered — always store/query the low id first."""
    a, b = int(a), int(b)
    return (a, b) if a <= b else (b, a)


def init_db(path=None):
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS reviews (
        record_a INTEGER NOT NULL,
        record_b INTEGER NOT NULL,
        action   TEXT NOT NULL CHECK(action IN ('approve','reject')),
        ts       REAL NOT NULL,
        steward  TEXT NOT NULL,
        note     TEXT,
        PRIMARY KEY (record_a, record_b)
    )""")
    # Maker-checker columns, added in place so an existing steward.db from an
    # earlier run keeps its decisions instead of being thrown away.
    existing = {r[1] for r in conn.execute("PRAGMA table_info(reviews)")}
    for col, ddl in (("status", "TEXT NOT NULL DEFAULT 'applied'"),
                     ("value_at_stake", "REAL NOT NULL DEFAULT 0"),
                     ("second_by", "TEXT"),
                     ("second_ts", "REAL")):
        if col not in existing:
            conn.execute(f"ALTER TABLE reviews ADD COLUMN {col} {ddl}")
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        ts       REAL NOT NULL,
        action   TEXT NOT NULL,
        record_a INTEGER,
        record_b INTEGER,
        steward  TEXT,
        detail   TEXT
    )""")
    conn.commit()
    return conn


def _log(conn, action, a, b, steward, detail):
    conn.execute(
        "INSERT INTO audit_log (ts, action, record_a, record_b, steward, detail) "
        "VALUES (?,?,?,?,?,?)",
        (time.time(), action, a, b, steward, detail),
    )


def record_review(conn, a, b, action, steward, note="", value_at_stake=0.0,
                  needs_second=False):
    """Record a decision. A high-value approve is parked, not applied.

    Returns the row's status: 'applied' or 'awaiting_second'. A *reject* is
    never parked - declining to merge is the safe direction, and making the
    cautious action harder than the risky one is how two-person rules get
    worked around in practice.
    """
    a, b = _key(a, b)
    steward = (steward or "steward_demo").strip() or "steward_demo"
    status = "awaiting_second" if (action == "approve" and needs_second) else "applied"
    conn.execute(
        "INSERT INTO reviews (record_a, record_b, action, ts, steward, note, status,"
        " value_at_stake, second_by, second_ts) VALUES (?,?,?,?,?,?,?,?,NULL,NULL) "
        "ON CONFLICT(record_a, record_b) DO UPDATE SET "
        "action=excluded.action, ts=excluded.ts, steward=excluded.steward, "
        "note=excluded.note, status=excluded.status, value_at_stake=excluded.value_at_stake,"
        " second_by=NULL, second_ts=NULL",
        (a, b, action, time.time(), steward, note or "", status, float(value_at_stake or 0)),
    )
    detail = note or ""
    if status == "awaiting_second":
        detail = (f"{detail} [parked: Rs {float(value_at_stake):,.0f} at stake, "
                  f"needs a second approver]").strip()
    _log(conn, action, a, b, steward, detail)
    conn.commit()
    return status


def countersign(conn, a, b, approver):
    """The second half of the two-person rule.

    Refuses if the countersigner is the same person who proposed the merge.
    Returns (ok, message).
    """
    a, b = _key(a, b)
    row = conn.execute(
        "SELECT action, steward, status, value_at_stake FROM reviews"
        " WHERE record_a=? AND record_b=?", (a, b)).fetchone()
    if not row:
        return False, "no decision to countersign"
    if row[2] != "awaiting_second":
        return False, f"this pair is already '{row[2]}'"
    if row[1] == approver:
        return False, ("the same person cannot propose and countersign a merge - "
                       "that is the whole point of the second signature")
    conn.execute("UPDATE reviews SET status='applied', second_by=?, second_ts=?"
                 " WHERE record_a=? AND record_b=?", (approver, time.time(), a, b))
    _log(conn, "countersign", a, b, approver,
         f"countersigned {row[1]}'s merge; Rs {float(row[3]):,.0f} at stake")
    conn.commit()
    return True, "applied"


def pending_second_approval(conn, limit=200):
    rows = conn.execute(
        "SELECT record_a, record_b, ts, steward, note, value_at_stake FROM reviews"
        " WHERE status='awaiting_second' ORDER BY value_at_stake DESC LIMIT ?",
        (limit,)).fetchall()
    return [dict(a=r[0], b=r[1], ts=r[2], steward=r[3], note=r[4], value_at_stake=r[5])
            for r in rows]


def get_review(conn, a, b):
    a, b = _key(a, b)
    row = conn.execute(
        "SELECT action, ts, steward, note FROM reviews WHERE record_a=? AND record_b=?",
        (a, b),
    ).fetchone()
    if not row:
        return None
    return dict(action=row[0], ts=row[1], steward=row[2], note=row[3])


def reviewed_keys(conn):
    """Every (a,b) pair a steward has already acted on, either direction."""
    return {(r[0], r[1]) for r in conn.execute("SELECT record_a, record_b FROM reviews")}


def approved_edges(conn):
    """Only edges that are actually in force. A merge parked for a second
    signature must not form a golden record in the meantime - if it did, the
    two-person rule would be decoration."""
    return [(r[0], r[1]) for r in conn.execute(
        "SELECT record_a, record_b FROM reviews WHERE action='approve' AND status='applied'")]


def remove_approved_edges_for_record(conn, record_id, steward, note=""):
    """Un-merge: drop every approved edge touching this record, splitting it
    out of whatever group it was in. The other members of the group stay
    merged with each other."""
    record_id = int(record_id)
    rows = conn.execute(
        "SELECT record_a, record_b FROM reviews WHERE action='approve' "
        "AND (record_a=? OR record_b=?)", (record_id, record_id),
    ).fetchall()
    for a, b in rows:
        conn.execute("DELETE FROM reviews WHERE record_a=? AND record_b=?", (a, b))
        _log(conn, "unmerge", a, b, steward, note or f"record {record_id} split out")
    conn.commit()
    return len(rows)


def audit_log(conn, limit=200):
    rows = conn.execute(
        "SELECT id, ts, action, record_a, record_b, steward, detail "
        "FROM audit_log ORDER BY id DESC LIMIT ?", (limit,),
    ).fetchall()
    return [dict(id=r[0], ts=r[1], action=r[2], record_a=r[3], record_b=r[4],
                 steward=r[5], detail=r[6]) for r in rows]


def counts(conn):
    approved = conn.execute(
        "SELECT COUNT(*) FROM reviews WHERE action='approve' AND status='applied'").fetchone()[0]
    rejected = conn.execute("SELECT COUNT(*) FROM reviews WHERE action='reject'").fetchone()[0]
    parked = conn.execute(
        "SELECT COUNT(*) FROM reviews WHERE status='awaiting_second'").fetchone()[0]
    return dict(approved=approved, rejected=rejected, awaiting_second=parked)
