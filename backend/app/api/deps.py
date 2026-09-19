"""Request dependencies: session, current user, role gates, CSRF."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..db import get_db
from ..models import User
from ..services import auth_service

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def current_session(request: Request, db: DbSession = Depends(get_db)):
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    return auth_service.session_for_token(db, token)


def current_user(request: Request, db: DbSession = Depends(get_db)) -> User:
    sess = current_session(request, db)
    if sess is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthenticated", "message": "not signed in"},
        )
    # CSRF: a cookie alone must never authorise a write.
    if request.method not in SAFE_METHODS and request.cookies.get(
            settings.SESSION_COOKIE_NAME):
        sent = request.headers.get(settings.CSRF_HEADER)
        if not sent or sent != sess.csrf_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "csrf_failed",
                        "message": f"missing or invalid {settings.CSRF_HEADER} header"},
            )
    request.state.session = sess
    return sess.user


def require_role(role: str):
    """401 when not signed in, 403 when signed in but junior — kept distinct so a
    UI can tell a viewer they need a different role instead of bouncing them to
    the login page forever."""
    def dep(user: User = Depends(current_user)) -> User:
        if not auth_service.has_role(user, role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "forbidden",
                        "message": f"this action needs the '{role}' role; "
                                   f"you hold '{user.role}'",
                        "required": role, "held": user.role},
            )
        return user
    return dep


require_viewer = require_role("viewer")
require_steward = require_role("steward")
require_approver = require_role("approver")
require_admin = require_role("admin")
