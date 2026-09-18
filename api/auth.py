"""Accounts, roles and sessions.

Until now every steward action was attributed to a free-text name field, which
means the audit trail said "Ramesh" and proved nothing. For a system that
rewrites codes in a public-sector ERP that is not a small gap: the audit trail
*is* the deliverable as far as a vigilance officer is concerned.

Four roles, each strictly containing the one below it:

    viewer     read the queues, the evidence and the catalogue
    steward    propose: approve or reject a pair
    approver   everything a steward does, plus countersign a high-value merge
    admin      manage accounts, issue and revoke ERP batches

**Maker-checker.**  A merge whose two records carry more than
`SECOND_APPROVAL_VALUE` of stock between them does not take effect when a
steward approves it. It is parked awaiting a *different* person holding the
approver role. Self-countersigning is refused even for admins. This is the
ordinary two-person rule that every CPSE already applies to purchase
decisions, and applying it to code merges is the reason a materials manager
will believe the rest of the system.

**Password storage.**  PBKDF2-HMAC-SHA256, 240,000 iterations, 16-byte random
salt per user, constant-time comparison. No third-party crypto library is
installable here (PyPI is blocked, as documented throughout) but PBKDF2 is in
the standard library and is a correct choice, not a fallback - the thing to
avoid was a bare SHA-256 of the password, and that is avoided. Argon2id would
be the upgrade, and is a one-function change in `_hash`.

Sessions are opaque 32-byte random tokens with an absolute expiry, stored
server-side so that revoking one actually revokes it. Nothing about the user
travels in the token, so there is no signature to verify and nothing to forge.
"""
import functools
import hashlib
import hmac
import os
import secrets
import time

from flask import g, jsonify, request

ROLES = ["viewer", "steward", "approver", "admin"]
RANK = {r: i for i, r in enumerate(ROLES)}

SESSION_TTL = 12 * 3600          # a working day
PBKDF2_ROUNDS = 240_000
SECOND_APPROVAL_VALUE = 1_000_000.0    # rupees of stock at stake

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username   TEXT PRIMARY KEY,
    full_name  TEXT NOT NULL,
    cpse       TEXT,
    role       TEXT NOT NULL,
    salt       BLOB NOT NULL,
    pwd_hash   BLOB NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1,
    created_ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    issued_ts  REAL NOT NULL,
    expires_ts REAL NOT NULL
);
"""

# Seeded so the console is usable the moment it starts. These are demo
# credentials in a demo database and are printed on startup; the point is to
# show the roles working, not to pretend this is a credential store.
SEED_USERS = [
    ("viewer",   "V. Iyer (audit)",      "CPCL", "viewer",   "viewer123"),
    ("steward",  "R. Mishra",            "IOCL", "steward",  "steward123"),
    ("approver", "S. Nair (materials)",  "IOCL", "approver", "approver123"),
    ("admin",    "System Administrator", "-",    "admin",    "admin123"),
]


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)


def init_auth(conn, seed=True):
    conn.executescript(SCHEMA)
    if seed and not conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        for username, full_name, cpse, role, pwd in SEED_USERS:
            create_user(conn, username, full_name, cpse, role, pwd)
    conn.commit()
    return conn


def create_user(conn, username, full_name, cpse, role, password):
    if role not in RANK:
        raise ValueError(f"unknown role {role!r}")
    salt = os.urandom(16)
    conn.execute(
        "INSERT INTO users (username, full_name, cpse, role, salt, pwd_hash, active, created_ts)"
        " VALUES (?,?,?,?,?,?,1,?)",
        (username, full_name, cpse, role, salt, _hash(password, salt), time.time()))
    conn.commit()
    return username


def verify(conn, username, password):
    row = conn.execute(
        "SELECT username, full_name, cpse, role, salt, pwd_hash, active FROM users"
        " WHERE username=?", (username,)).fetchone()
    if not row:
        # Spend the same work on an unknown user as on a known one, so response
        # time does not reveal which usernames exist.
        _hash(password, b"0" * 16)
        return None
    if not row[6]:
        return None
    if not hmac.compare_digest(row[5], _hash(password, row[4])):
        return None
    return dict(username=row[0], full_name=row[1], cpse=row[2], role=row[3])


def login(conn, username, password):
    user = verify(conn, username, password)
    if not user:
        return None
    token = secrets.token_urlsafe(32)
    now = time.time()
    conn.execute("INSERT INTO sessions (token, username, issued_ts, expires_ts) VALUES (?,?,?,?)",
                 (token, username, now, now + SESSION_TTL))
    conn.commit()
    return dict(token=token, expires_ts=now + SESSION_TTL, **user)


def logout(conn, token):
    conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    conn.commit()


def user_for_token(conn, token):
    if not token:
        return None
    row = conn.execute(
        "SELECT u.username, u.full_name, u.cpse, u.role, s.expires_ts FROM sessions s"
        " JOIN users u ON u.username = s.username WHERE s.token=? AND u.active=1",
        (token,)).fetchone()
    if not row:
        return None
    if row[4] < time.time():
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
        return None
    return dict(username=row[0], full_name=row[1], cpse=row[2], role=row[3])


def purge_expired(conn):
    conn.execute("DELETE FROM sessions WHERE expires_ts < ?", (time.time(),))
    conn.commit()


def can(user, role):
    return bool(user) and RANK.get(user["role"], -1) >= RANK[role]


def token_from_request():
    hdr = request.headers.get("Authorization", "")
    if hdr.lower().startswith("bearer "):
        return hdr[7:].strip()
    return request.headers.get("X-Session-Token") or request.cookies.get("samanvay_session")


def requires(role, conn_getter):
    """Flask decorator. 401 when not signed in, 403 when signed in but junior.

    The two are kept distinct because conflating them is how a UI ends up
    bouncing a signed-in viewer to the login page over and over instead of
    telling them they need a different role.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            user = user_for_token(conn_getter(), token_from_request())
            if not user:
                return jsonify(error="not signed in", code="unauthenticated"), 401
            if not can(user, role):
                return jsonify(error=f"this action needs the '{role}' role; "
                                     f"you hold '{user['role']}'",
                               code="forbidden", required=role, held=user["role"]), 403
            g.user = user
            return fn(*args, **kwargs)
        return wrapper
    return deco


def needs_second_approval(value_at_stake):
    return float(value_at_stake or 0) >= SECOND_APPROVAL_VALUE
