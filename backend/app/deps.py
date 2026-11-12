"""Request-level security: session lookup, CSRF + Origin checks and role guards.

Every authenticated request must carry the HttpOnly session cookie. Unsafe methods (POST/PATCH/DELETE) must also
send the per-session token in the X-CSRF-Token header (synchronizer-token pattern), and if the browser sends an
Origin header it must be one of the allowed origins. The CSRF token is only ever returned in a JSON response to
the logged-in page, so a third-party site cannot read it.
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import config
from .db import get_db, utcnow
from .models import AuthSession, User
from .security import hash_token

COOKIE_NAME = "creditlens_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _unauthorized(msg: str = "Please log in.") -> HTTPException:
    return HTTPException(status_code=401, detail=msg)


def load_session(request: Request, db: Session) -> tuple[User, AuthSession]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise _unauthorized()
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    now = utcnow()
    if sess is None:
        raise _unauthorized("Session not found. Please log in again.")
    if sess.expires_at < now:
        db.execute(delete(AuthSession).where(AuthSession.id == sess.id))
        db.commit()
        raise _unauthorized("Session expired. Please log in again.")
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Account is not active.")
    if now - sess.last_seen > timedelta(minutes=1):
        sess.last_seen = now
        db.commit()
    return user, sess


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in config.cors_origins():
        raise HTTPException(status_code=403, detail="Origin not allowed.")


def authenticated_user(request: Request, db: Session = Depends(get_db)) -> User:
    user, sess = load_session(request, db)
    if request.method not in SAFE_METHODS:
        check_origin(request)
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not secrets.compare_digest(sent, sess.csrf_token):
            raise HTTPException(status_code=403, detail="Missing or invalid CSRF token.")
    request.state.session = sess
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(authenticated_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        return user
    return dependency


applicant_user = require_roles("applicant")
reviewer_user = require_roles("reviewer")
admin_user = require_roles("admin")
staff_user = require_roles("reviewer", "admin")
