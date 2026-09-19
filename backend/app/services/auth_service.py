"""Authentication, sessions and the role hierarchy.

Argon2id replaces the prototype's PBKDF2. Sessions stay server-side and opaque:
nothing about the user travels in the token, so there is no signature to forge,
and deleting the row actually revokes access.

The browser holds the session in an HttpOnly cookie, which means the API needs
CSRF protection on state-changing calls; the session carries a second, separate
token the frontend echoes in a header. A cookie alone is never sufficient
authorisation for a write.
"""
from __future__ import annotations

import datetime as dt
import secrets

from passlib.context import CryptContext
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..models import Session, User

ROLES = ("viewer", "steward", "approver", "admin")
RANK = {r: i for i, r in enumerate(ROLES)}

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(pw: str) -> str:
    return pwd_context.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(pw, hashed)
    except Exception:
        return False


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def authenticate(db: DbSession, username: str, password: str) -> User | None:
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        # Spend comparable work on an unknown user so response time does not
        # reveal which usernames exist.
        pwd_context.hash("timing-equaliser")
        return None
    if not user.is_active or not verify_password(password, user.password_hash):
        return None
    return user


def create_session(db: DbSession, user: User, user_agent: str | None = None,
                   ip: str | None = None) -> Session:
    now = _now()
    s = Session(
        token=secrets.token_urlsafe(32),
        csrf_token=secrets.token_urlsafe(24),
        user_id=user.id,
        issued_at=now,
        expires_at=now + dt.timedelta(seconds=settings.SESSION_TTL_SECONDS),
        user_agent=(user_agent or "")[:300] or None,
        ip_address=(ip or "")[:64] or None,
    )
    user.last_login_at = now
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def session_for_token(db: DbSession, token: str | None) -> Session | None:
    if not token:
        return None
    s = db.get(Session, token)
    if s is None:
        return None
    if s.expires_at <= _now():
        db.delete(s)
        db.commit()
        return None
    return s


def revoke(db: DbSession, token: str) -> None:
    db.execute(delete(Session).where(Session.token == token))
    db.commit()


def purge_expired(db: DbSession) -> int:
    r = db.execute(delete(Session).where(Session.expires_at < _now()))
    db.commit()
    return r.rowcount or 0


def has_role(user: User, required: str) -> bool:
    return RANK.get(user.role, -1) >= RANK[required]


def needs_second_approval(value_at_stake: float) -> bool:
    """A merge carrying more than the threshold of stock needs two people."""
    return float(value_at_stake or 0) >= settings.SECOND_APPROVAL_VALUE
