"""Registration, login, logout and session info.

Public registration always creates an APPLICANT. Reviewer and admin accounts can only be created by an
administrator (API or `python -m app.admin`). Login failures return one generic message, and repeated failures
lock the account temporarily.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import config
from .audit import log_event
from .db import get_db, utcnow
from .deps import COOKIE_NAME, authenticated_user, check_origin
from .models import AuthSession, ConsentRecord, User
from .notice import NOTICE_TEXT, NOTICE_VERSION
from .security import (DUMMY_HASH, EMAIL_RE, hash_password, hash_token, new_token, normalize_email,
                       password_problems, verify_password)

router = APIRouter(prefix="/api/v1", tags=["auth"])
GENERIC_LOGIN_ERROR = "Invalid email or password."


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    accept_notice_version: str = Field(max_length=40)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


def user_view(u: User) -> dict:
    return {"id": u.id, "email": u.email, "role": u.role}


def start_session(db: Session, user: User, response: Response) -> str:
    token, csrf = new_token(), new_token()
    now = utcnow()
    db.add(AuthSession(user_id=user.id, token_hash=hash_token(token), csrf_token=csrf, created_at=now,
                       last_seen=now, expires_at=now + timedelta(hours=config.session_hours())))
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", secure=config.cookie_secure(),
                        max_age=config.session_hours() * 3600, path="/")
    return csrf


@router.get("/consent/notice")
def consent_notice():
    return {"version": NOTICE_VERSION, "text": NOTICE_TEXT}


@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    email = normalize_email(body.email)
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if body.accept_notice_version != NOTICE_VERSION:
        raise HTTPException(status_code=422, detail="You must accept the current data-use notice to register.")
    problems = password_problems(body.password, email)
    if problems:
        raise HTTPException(status_code=422, detail="Password " + "; ".join(problems) + ".")
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(email=email, password_hash=hash_password(body.password), role="applicant")
    db.add(user)
    db.flush()
    db.add(ConsentRecord(user_id=user.id, notice_version=body.accept_notice_version))
    log_event(db, user, "auth.registered", "user", user.id)
    csrf = start_session(db, user, response)
    db.commit()
    return {"user": user_view(user), "csrf_token": csrf}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    email = normalize_email(body.email)
    user = db.scalar(select(User).where(User.email == email))
    now = utcnow()
    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Please try again later.")
    ok = verify_password(user.password_hash if user else DUMMY_HASH, body.password) and user is not None and user.is_active
    if not ok:
        if user:
            user.failed_logins += 1
            if user.failed_logins >= config.max_failed_logins():
                user.locked_until = now + timedelta(minutes=config.lockout_minutes())
                user.failed_logins = 0
        log_event(db, None, "auth.login_failed", "user", user.id if user else "unknown")
        db.commit()
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)
    user.failed_logins, user.locked_until = 0, None
    csrf = start_session(db, user, response)           # new session id on every login (no fixation)
    log_event(db, user, "auth.login", "user", user.id)
    db.commit()
    return {"user": user_view(user), "csrf_token": csrf}


@router.post("/auth/logout")
def logout(request: Request, response: Response, user: User = Depends(authenticated_user), db: Session = Depends(get_db)):
    sess = request.state.session
    db.execute(delete(AuthSession).where(AuthSession.id == sess.id))
    log_event(db, user, "auth.logout", "user", user.id)
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request, user: User = Depends(authenticated_user)):
    return {"user": user_view(user), "csrf_token": request.state.session.csrf_token}
