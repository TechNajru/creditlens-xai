"""Administrator: users, model versions, monitoring and audit. Admins do not see application content."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import registry
from .app_service import iso
from .audit import event_view, log_event, verify_chain
from .db import get_db
from .deps import admin_user
from .models import Application, AuditEvent, AuthSession, ModelVersion, User
from .monitoring import monitoring_summary
from .security import EMAIL_RE, hash_password, normalize_email, password_problems

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
Role = Literal["applicant", "reviewer", "admin"]


class CreateUserIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    role: Role


class UpdateUserIn(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class RegisterModelIn(BaseModel):
    track: Literal["simulation", "public"]


def _user_row(u: User, apps: int = 0) -> dict:
    return {"id": u.id, "email": u.email, "role": u.role, "is_active": u.is_active, "created_at": iso(u.created_at),
            "applications": apps}


def _model_row(m: ModelVersion) -> dict:
    return {"id": m.id, "track": m.track, "version": m.version, "artifact_sha256": m.artifact_sha256,
            "is_active": m.is_active, "registered_at": iso(m.registered_at), "activated_at": iso(m.activated_at),
            "summary": m.metadata_json}


@router.get("/users")
def list_users(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.id)).all()
    counts = {}
    for uid in db.scalars(select(Application.user_id)):
        counts[uid] = counts.get(uid, 0) + 1
    return {"users": [_user_row(u, counts.get(u.id, 0)) for u in users]}


@router.post("/users", status_code=201)
def create_user(body: CreateUserIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    email = normalize_email(body.email)
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    problems = password_problems(body.password, email)
    if problems:
        raise HTTPException(status_code=422, detail="Password " + "; ".join(problems) + ".")
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    u = User(email=email, password_hash=hash_password(body.password), role=body.role)
    db.add(u)
    db.flush()
    log_event(db, admin, "user.created", "user", u.id, details={"role": u.role})
    db.commit()
    return _user_row(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UpdateUserIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if u.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot change your own role or active status.")
    if body.role is not None and body.role != u.role:
        log_event(db, admin, "user.role_changed", "user", u.id, details={"role_from": u.role, "role_to": body.role})
        u.role = body.role
        db.execute(delete(AuthSession).where(AuthSession.user_id == u.id))     # force re-login with the new role
    if body.is_active is not None and body.is_active != u.is_active:
        u.is_active = body.is_active
        log_event(db, admin, "user.activation_changed", "user", u.id, details={"active": u.is_active})
        if not u.is_active:
            db.execute(delete(AuthSession).where(AuthSession.user_id == u.id))
    db.commit()
    return _user_row(u)


@router.get("/models")
def list_models(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    models = db.scalars(select(ModelVersion).order_by(ModelVersion.track, ModelVersion.id.desc())).all()
    return {"models": [_model_row(m) for m in models]}


@router.post("/models/register", status_code=201)
def register_model(body: RegisterModelIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    try:
        mv, created = registry.register_artifact(db, body.track, admin)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return {**_model_row(mv), "newly_registered": created}


@router.post("/models/{model_id}/activate")
def activate_model(model_id: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    mv = db.get(ModelVersion, model_id)
    if mv is None:
        raise HTTPException(status_code=404, detail="Model version not found.")
    registry.activate(db, mv, admin)
    db.commit()
    return _model_row(mv)


@router.get("/monitoring")
def monitoring(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    return monitoring_summary(db)


@router.get("/audit")
def audit(limit: int = Query(100, ge=1, le=500), application_id: str | None = None,
          admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if application_id:
        q = select(AuditEvent).where(AuditEvent.application_id == application_id).order_by(AuditEvent.id.desc()).limit(limit)
    return {"events": [event_view(e) for e in db.scalars(q)]}


@router.get("/audit/verify")
def audit_verify(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    return verify_chain(db)
