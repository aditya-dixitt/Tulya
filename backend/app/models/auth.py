"""Accounts, roles and server-side sessions.

Carried over from the prototype's `api/auth.py` with three changes:

  * storage moves to PostgreSQL;
  * password hashing moves from PBKDF2 to Argon2id (passlib), because
    argon2-cffi is installable here and PBKDF2 was only ever chosen because it
    was in the standard library;
  * sessions gain a CSRF token, because the browser now authenticates with an
    HttpOnly cookie rather than a bearer header the frontend pasted in.

The four roles and the maker-checker rule are unchanged. They are the part a
vigilance officer cares about and there was no reason to redesign them.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(200), unique=True)
    cpse_id: Mapped[int | None] = mapped_column(ForeignKey("cpses.id"))
    role: Mapped[str] = mapped_column(String(16), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username} ({self.role})>"


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_expiry", "expires_at"),)

    # Opaque random token. Nothing about the user travels inside it, so there
    # is no signature to forge and revoking a row actually revokes access.
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    issued_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip_address: Mapped[str | None] = mapped_column(String(64))

    user: Mapped["User"] = relationship(back_populates="sessions")
