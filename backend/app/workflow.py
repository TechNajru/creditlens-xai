"""Application state machine. Every status change goes through transition() so it is validated and audited.

draft -> submitted -> validation -> assessed -> manual_review -> final_demo_decision
                          |                          |
                          v                          v
                        draft                 info_requested -> submitted (applicant resubmits)
"""
from __future__ import annotations

from .audit import log_event
from .db import utcnow

STATES = ("draft", "submitted", "validation", "assessed", "manual_review", "info_requested", "final_demo_decision")
TRANSITIONS = {
    "draft": {"submitted"},
    "submitted": {"validation"},
    "validation": {"assessed", "draft"},          # validation failure returns the application to draft
    "assessed": {"manual_review"},
    "manual_review": {"info_requested", "final_demo_decision"},
    "info_requested": {"submitted"},
    "final_demo_decision": set(),
}
EDITABLE = frozenset({"draft", "info_requested"})   # applicant may change inputs/uploads only in these states
DELETABLE = frozenset({"draft", "info_requested", "final_demo_decision"})   # not while a reviewer is working on it
VISIBLE_TO_REVIEWERS = frozenset({"manual_review", "info_requested", "final_demo_decision"})


class InvalidTransition(ValueError):
    pass


def transition(db, application, new_status: str, actor, details: dict | None = None) -> None:
    old = application.status
    if new_status not in TRANSITIONS.get(old, set()):
        raise InvalidTransition(f"Cannot move an application from '{old}' to '{new_status}'")
    application.status = new_status
    application.updated_at = utcnow()
    log_event(db, actor, "application.status_changed", "application", application.id, application.id,
              {"status_from": old, "status_to": new_status, **(details or {})})
