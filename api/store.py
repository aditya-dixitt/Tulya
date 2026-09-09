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


def record_review(conn, a, b, action, steward, note=""):
    a, b = _key(a, b)
    steward = (steward or "steward_demo").strip() or "steward_demo"
    conn.execute(
        "INSERT INTO reviews (record_a, record_b, action, ts, steward, note) "
        "VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(record_a, record_b) DO UPDATE SET "
        "action=excluded.action, ts=excluded.ts, steward=excluded.steward, note=excluded.note",
        (a, b, action, time.time(), steward, note or ""),
    )
    _log(conn, action, a, b, steward, note or "")
    conn.commit()


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
    return [(r[0], r[1]) for r in
            conn.execute("SELECT record_a, record_b FROM reviews WHERE action='approve'")]


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
    approved = conn.execute("SELECT COUNT(*) FROM reviews WHERE action='approve'").fetchone()[0]
    rejected = conn.execute("SELECT COUNT(*) FROM reviews WHERE action='reject'").fetchone()[0]
    return dict(approved=approved, rejected=rejected)
