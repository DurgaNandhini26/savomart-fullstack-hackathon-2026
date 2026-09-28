"""Property pipeline: an explicit state machine with an audit trail.

 submitted ──► shortlisted ──► site_visit ──► negotiation ──► approved
     │  ▲           │  catchment_study ◄──┘        │
     │  └ info_requested (exec answers)            │
     └──────────► rejected / on_hold / duplicate ◄──┘

Every transition needs a note (the "why"); rejections also need a reason category.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Property, PropertyEvent, User

STAGES = {
    "submitted": "New — awaiting review",
    "info_requested": "Info requested from executive",
    "shortlisted": "Shortlisted",
    "site_visit": "Site visit",
    "catchment_study": "Catchment study",
    "negotiation": "Negotiation",
    "approved": "Approved",
    "rejected": "Rejected",
    "on_hold": "On hold",
    "duplicate": "Duplicate",
}
ACTIVE_ORDER = ["submitted", "info_requested", "shortlisted", "site_visit", "catchment_study", "negotiation", "approved"]

TRANSITIONS: dict[str, list[str]] = {
    "submitted": ["shortlisted", "info_requested", "catchment_study", "rejected", "on_hold", "duplicate"],
    "info_requested": ["submitted", "rejected", "on_hold"],
    "shortlisted": ["site_visit", "catchment_study", "negotiation", "info_requested", "rejected", "on_hold"],
    "site_visit": ["catchment_study", "negotiation", "info_requested", "rejected", "on_hold"],
    "catchment_study": ["site_visit", "negotiation", "rejected", "on_hold"],
    "negotiation": ["approved", "rejected", "on_hold"],
    "on_hold": ["submitted", "shortlisted", "rejected"],
    "rejected": ["submitted"],
    "duplicate": ["submitted"],
    "approved": [],
}
# Executives may only answer an info request; everything else is a manager decision.
EXEC_TRANSITIONS = {("info_requested", "submitted")}
REJECT_REASONS = ["rent_too_high", "size_unsuitable", "poor_visibility", "weak_catchment", "too_close_to_store",
                  "legal_or_title_issue", "owner_withdrew", "other"]


class TransitionError(ValueError):
    pass


def allowed_next(prop: Property, user: User) -> list[str]:
    nxt = TRANSITIONS.get(prop.stage, [])
    if user.role == "bd_manager":
        return nxt
    if user.role == "bd_exec" and prop.submitted_by_id == user.id:
        return [s for s in nxt if (prop.stage, s) in EXEC_TRANSITIONS]
    return []


def transition(db: Session, prop: Property, user: User, to: str, note: str | None,
               reason: str | None = None, meta: dict | None = None) -> PropertyEvent:
    if to not in STAGES:
        raise TransitionError(f"Unknown stage {to}")
    if to not in allowed_next(prop, user):
        raise TransitionError(f"{user.name} cannot move a property from '{STAGES[prop.stage]}' to '{STAGES[to]}'")
    if not (note or "").strip():
        raise TransitionError("Please add a note explaining why.")
    if to == "rejected" and reason not in REJECT_REASONS:
        raise TransitionError(f"Rejections need a reason: {', '.join(REJECT_REASONS)}")
    ev = PropertyEvent(property_id=prop.id, actor_id=user.id, action="stage_change", from_stage=prop.stage,
                       to_stage=to, note=note.strip(), meta={**(meta or {}), **({"reason": reason} if reason else {})})
    prop.stage = to
    db.add(ev)
    return ev


def log(db: Session, prop: Property, user: User | None, action: str, note: str | None = None,
        meta: dict | None = None) -> None:
    db.add(PropertyEvent(property_id=prop.id, actor_id=user.id if user else None, action=action,
                         from_stage=prop.stage, to_stage=prop.stage, note=note, meta=meta))
