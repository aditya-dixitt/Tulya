"""Sign in, sign out, who am I.

The session lands in an HttpOnly cookie; the CSRF token is returned in the body
for the frontend to echo on writes. The token is never placed in a JS-readable
cookie, which is the mistake that makes HttpOnly pointless.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as DbSession

from ...config import settings
from ...db import get_db
from ...models import AuditEvent, User
from ...schemas.auth import LoginRequest, SessionOut, UserOut
from ...services import auth_service
from ..deps import current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=SessionOut, summary="Sign in")
def login(body: LoginRequest, request: Request, response: Response,
          db: DbSession = Depends(get_db)) -> SessionOut:
    user = auth_service.authenticate(db, body.username, body.password)
    if user is None:
        # One message for both cases. Telling an attacker which half was wrong
        # is a free username oracle.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials",
                    "message": "username or password is incorrect"},
        )
    sess = auth_service.create_session(
        db, user,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    db.add(AuditEvent(action="auth.login", entity_type="user", entity_id=user.id,
                      actor_id=user.id, actor_username=user.username,
                      request_id=getattr(request.state, "request_id", None),
                      detail=f"signed in as {user.role}"))
    db.commit()
    response.set_cookie(
        settings.SESSION_COOKIE_NAME, sess.token, httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        max_age=settings.SESSION_TTL_SECONDS, path="/",
    )
    return SessionOut(user=UserOut.model_validate(user),
                      csrf_token=sess.csrf_token,
                      expires_at=sess.expires_at.isoformat())


@router.post("/logout", summary="Sign out")
def logout(request: Request, response: Response, db: DbSession = Depends(get_db)) -> dict:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if token:
        auth_service.revoke(db, token)
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
    return {"status": "signed_out"}


@router.get("/me", response_model=UserOut, summary="Current user")
def me(user: User = Depends(current_user)) -> UserOut:
    return UserOut.model_validate(user)
