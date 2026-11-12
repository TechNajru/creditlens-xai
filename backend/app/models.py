"""ORM models. Generic SQL types only so the schema also works on PostgreSQL."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow

ROLES = ("applicant", "reviewer", "admin")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role in ('applicant','reviewer','admin')", name="ck_users_role"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="applicant")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuthSession(Base):
    """Server-side session. Only a SHA-256 of the cookie token is stored, so a database leak is not a session leak."""
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    notice_version: Mapped[str] = mapped_column(String(40))
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("track", "artifact_sha256", name="uq_model_track_sha"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track: Mapped[str] = mapped_column(String(20))            # simulation | public
    version: Mapped[str] = mapped_column(String(200))
    artifact_sha256: Mapped[str] = mapped_column(String(64))
    artifact_path: Mapped[str] = mapped_column(String(500))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)        # random UUID: not guessable
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    loan_inputs: Mapped[dict] = mapped_column(JSON)
    review_reasons: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    upload: Mapped["Upload | None"] = relationship(back_populates="application", cascade="all, delete-orphan", uselist=False)
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="application", cascade="all, delete-orphan", order_by="Assessment.id")
    info_requests: Mapped[list["InfoRequest"]] = relationship(back_populates="application", cascade="all, delete-orphan", order_by="InfoRequest.id")
    decisions: Mapped[list["ReviewDecision"]] = relationship(back_populates="application", cascade="all, delete-orphan", order_by="ReviewDecision.id")


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    rows_total: Mapped[int] = mapped_column(Integer)
    rows_valid: Mapped[int] = mapped_column(Integer)
    rows_with_errors: Mapped[int] = mapped_column(Integer)
    duplicates_excluded: Mapped[int] = mapped_column(Integer)
    date_format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    issues: Mapped[list] = mapped_column(JSON, default=list)       # row number + field + reason only
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    application: Mapped[Application] = relationship(back_populates="upload")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="upload", cascade="all, delete-orphan", order_by="Transaction.id")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("upload_id", "key", name="uq_tx_upload_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(120))
    row: Mapped[int] = mapped_column(Integer)
    transaction_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(10))
    balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    category: Mapped[str] = mapped_column(String(40))
    category_source: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[str] = mapped_column(String(10))
    upload: Mapped[Upload] = relationship(back_populates="transactions")


class Assessment(Base):
    """Model output (never edited). Human decisions live in ReviewDecision."""
    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    is_preview: Mapped[bool] = mapped_column(Boolean, default=True)
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True)
    model_version: Mapped[str] = mapped_column(String(200))
    feature_schema_version: Mapped[str] = mapped_column(String(20))
    policy_version: Mapped[str] = mapped_column(String(40))
    calibration_method: Mapped[str] = mapped_column(String(20))
    default_probability: Mapped[float] = mapped_column(Float)
    uncalibrated_score: Mapped[float] = mapped_column(Float)
    policy_result: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)                      # full model response incl. provenance + limitations
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    application: Mapped[Application] = relationship(back_populates="assessments")
    feature_snapshot: Mapped["FeatureSnapshot | None"] = relationship(back_populates="assessment", cascade="all, delete-orphan", uselist=False)
    explanation: Mapped["Explanation | None"] = relationship(back_populates="assessment", cascade="all, delete-orphan", uselist=False)


class FeatureSnapshot(Base):
    __tablename__ = "feature_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), unique=True)
    input_snapshot: Mapped[dict] = mapped_column(JSON)
    features: Mapped[dict] = mapped_column(JSON)
    cashflow_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # descriptive; NOT a model input
    assessment: Mapped[Assessment] = relationship(back_populates="feature_snapshot")


class Explanation(Base):
    __tablename__ = "explanations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(20))
    method: Mapped[str | None] = mapped_column(String(200), nullable=True)
    version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    assessment: Mapped[Assessment] = relationship(back_populates="explanation")


class InfoRequest(Base):
    __tablename__ = "info_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    application: Mapped[Application] = relationship(back_populates="info_requests")


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision: Mapped[str] = mapped_column(String(20))               # demo_approved | demo_declined
    reason: Mapped[str] = mapped_column(Text)
    policy_recommendation: Mapped[str] = mapped_column(String(20))
    is_override: Mapped[bool] = mapped_column(Boolean, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    application: Mapped[Application] = relationship(back_populates="decisions")


class AuditEvent(Base):
    """Append-only, hash-chained. Holds ids and enums, never raw financial content."""
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)      # no FK: survives user removal
    actor_role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(60))
    application_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)   # no FK: survives deletion
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), unique=True)
