"""Append-only, hash-chained audit trail.

Each event stores sha256(prev_hash + canonical JSON of the event), so editing or deleting a past event
breaks every later hash and is caught by verify_chain(). This is tamper-EVIDENCE for a student project
(a database admin could still rewrite the whole chain); it is not a substitute for external log shipping.

Details are sanitised: only allow-listed keys, only short scalars. Raw financial content never enters the log.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import utcnow
from .models import AuditEvent

GENESIS = "0" * 64
ALLOWED_KEYS = {"status_from", "status_to", "decision", "is_override", "model_version", "policy_version", "role",
                "role_from", "role_to", "reason_count", "rows_valid", "rows_total", "active", "track", "is_preview",
                "changed_fields", "category_to", "ok", "count"}


def _clean(details: dict | None) -> dict:
    out = {}
    for k, v in (details or {}).items():
        if k not in ALLOWED_KEYS:
            continue
        if isinstance(v, (bool, int, float)) or v is None:
            out[k] = v
        elif isinstance(v, str) and len(v) <= 80:
            out[k] = v
        elif isinstance(v, (list, tuple)) and len(v) <= 12 and all(isinstance(x, str) and len(x) <= 40 for x in v):
            out[k] = list(v)
    return out


def _digest(prev_hash: str, body: dict) -> str:
    return hashlib.sha256((prev_hash + json.dumps(body, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()


def _body(ev: AuditEvent) -> dict:
    return {"ts": ev.ts.isoformat(timespec="microseconds"), "actor_id": ev.actor_id, "actor_role": ev.actor_role,
            "action": ev.action, "entity_type": ev.entity_type, "entity_id": ev.entity_id,
            "application_id": ev.application_id, "details": ev.details}


def log_event(db: Session, actor, action: str, entity_type: str, entity_id, application_id: str | None = None,
              details: dict | None = None) -> AuditEvent:
    prev = db.scalar(select(AuditEvent.event_hash).order_by(AuditEvent.id.desc()).limit(1)) or GENESIS
    ev = AuditEvent(ts=utcnow(), actor_id=getattr(actor, "id", None), actor_role=getattr(actor, "role", "system"),
                    action=action, entity_type=entity_type, entity_id=str(entity_id),
                    application_id=application_id, details=_clean(details), prev_hash=prev, event_hash="pending")
    ev.event_hash = _digest(prev, _body(ev))
    db.add(ev)
    db.flush()
    return ev


def verify_chain(db: Session) -> dict:
    prev, checked = GENESIS, 0
    for ev in db.scalars(select(AuditEvent).order_by(AuditEvent.id)):
        if ev.prev_hash != prev or ev.event_hash != _digest(prev, _body(ev)):
            return {"ok": False, "checked": checked, "first_bad_event_id": ev.id}
        prev, checked = ev.event_hash, checked + 1
    return {"ok": True, "checked": checked, "first_bad_event_id": None}


def event_view(ev: AuditEvent) -> dict:
    return {"id": ev.id, "ts": ev.ts.isoformat(timespec="seconds") + "Z", "actor_role": ev.actor_role,
            "actor_id": ev.actor_id, "action": ev.action, "entity_type": ev.entity_type, "entity_id": ev.entity_id,
            "application_id": ev.application_id, "details": ev.details}
