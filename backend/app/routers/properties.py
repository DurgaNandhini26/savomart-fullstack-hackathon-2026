"""M2 — property onboarding, evaluation and pipeline."""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import geo
from ..auth import current_user, require
from ..config import get_settings
from ..db import get_db
from ..models import (CatchmentStudy, Job, Property, PropertyEvaluation, PropertyEvent, PropertyPhoto, ScoutMission,
                      User)
from ..serializers import (PROPERTY_FIELDS, evaluation_dict, event_dict, property_full, property_summary,
                           study_summary)
from ..services import areas as A
from ..services import jobs
from ..services import pipeline as P
from ..services.notify import notify, role_users
from ..services.property_eval import new_evaluation

router = APIRouter(prefix="/api")
DUPLICATE_RADIUS_M = 40
PIN_DRIFT_WARN_M = 250
MAX_PHOTO_BYTES = 8 * 1024 * 1024


class PropertyIn(BaseModel):
    client_uuid: str | None = None
    mission_id: int | None = None
    title: str = Field(min_length=3, max_length=200)
    lat: float
    lng: float
    gps_accuracy_m: float | None = None
    device_lat: float | None = None
    device_lng: float | None = None
    address: str | None = None
    locality: str | None = None
    pincode: str | None = Field(None, pattern=r"^\d{6}$")
    property_type: str = Field(pattern="^(shop|showroom|standalone_building|ground_floor_residential|warehouse|land|other)$")
    carpet_area_sqft: float | None = Field(None, gt=0, lt=100000)
    frontage_ft: float | None = Field(None, gt=0, lt=1000)
    floor: str | None = Field(None, pattern="^(ground|first|ground\\+first|basement)$")
    ceiling_height_ft: float | None = Field(None, gt=0, lt=60)
    rent_monthly: float | None = Field(None, ge=0, lt=10_000_000)
    rent_negotiable: bool = False
    deposit_months: float | None = Field(None, ge=0, le=60)
    lease_years: float | None = Field(None, ge=0, le=99)
    parking_2w: int | None = Field(None, ge=0, le=500)
    parking_4w: int | None = Field(None, ge=0, le=200)
    road_facing: str | None = Field(None, pattern="^(main_road|secondary|interior)$")
    road_width_ft: float | None = Field(None, gt=0, lt=300)
    visibility: int | None = Field(None, ge=1, le=5)
    power_kw: float | None = Field(None, ge=0, lt=1000)
    truck_access: bool | None = None
    available_from: date | None = None
    owner_name: str | None = None
    owner_phone: str | None = Field(None, pattern=r"^[+\d][\d\s-]{6,18}$")
    notes: str | None = None
    confirm_not_duplicate: bool = False


def quality_checks(body: PropertyIn) -> list[str]:
    """Soft warnings about field input. Hard errors are raised by pydantic / create()."""
    w = []
    if body.device_lat is not None and body.device_lng is not None:
        drift = geo.haversine_m(body.lat, body.lng, body.device_lat, body.device_lng)
        if drift > PIN_DRIFT_WARN_M:
            w.append(f"Pin is {round(drift)} m from where the phone was when submitting — verify the location.")
    if body.gps_accuracy_m and body.gps_accuracy_m > 100:
        w.append(f"GPS accuracy was poor (±{round(body.gps_accuracy_m)} m).")
    if body.rent_monthly is None and not body.rent_negotiable:
        w.append("Rent not captured.")
    if body.rent_monthly and body.carpet_area_sqft:
        psf = body.rent_monthly / body.carpet_area_sqft
        if psf < 10 or psf > 400:
            w.append(f"Rent works out to ₹{psf:.0f}/sq ft/month, which looks unusual — check units (monthly vs annual, sq ft vs sq m).")
    if not body.carpet_area_sqft:
        w.append("Carpet area not captured.")
    return w


def find_duplicates(db: Session, lat: float, lng: float, exclude_id: int | None = None) -> list[dict]:
    d = 0.001
    out = []
    for p in db.scalars(select(Property).where(Property.lat.between(lat - d, lat + d), Property.lng.between(lng - d, lng + d))):
        if p.id == exclude_id:
            continue
        dist = geo.haversine_m(lat, lng, p.lat, p.lng)
        if dist <= DUPLICATE_RADIUS_M:
            out.append({**property_summary(p), "distance_m": round(dist)})
    return sorted(out, key=lambda x: x["distance_m"])


@router.post("/properties/check")
def precheck(body: PropertyIn, db: Session = Depends(get_db), _: User = Depends(require("bd_exec", "bd_manager"))):
    return {"warnings": quality_checks(body), "duplicates": find_duplicates(db, body.lat, body.lng),
            "in_region": geo.in_chennai(body.lat, body.lng)}


@router.post("/properties", status_code=201)
def create(body: PropertyIn, db: Session = Depends(get_db), user: User = Depends(require("bd_exec", "bd_manager"))):
    if body.client_uuid:  # idempotent: a retried offline submit returns the original
        existing = db.scalar(select(Property).where(Property.client_uuid == body.client_uuid))
        if existing:
            return {"property": property_full(existing), "duplicate_submit": True}
    if not geo.in_chennai(body.lat, body.lng):
        raise HTTPException(422, "That pin is outside the Chennai region — check the location.")
    if body.mission_id:
        m = db.get(ScoutMission, body.mission_id)
        if not m:
            raise HTTPException(422, "Unknown mission")
    dups = find_duplicates(db, body.lat, body.lng)
    if dups and not body.confirm_not_duplicate:
        raise HTTPException(409, {"message": "Possible duplicate: a property already exists within "
                                             f"{DUPLICATE_RADIUS_M} m.", "duplicates": dups})
    warnings = quality_checks(body)
    if dups:
        warnings.append(f"Submitted despite {len(dups)} nearby existing propert{'y' if len(dups) == 1 else 'ies'} "
                        f"({', '.join(d['code'] for d in dups)}) — executive confirmed it is a different unit.")
    data = body.model_dump(exclude={"confirm_not_duplicate"})
    if not data.get("locality"):
        data["locality"] = A.nearest_locality(db, body.lat, body.lng)
    n = (db.scalar(select(func.max(Property.id))) or 0) + 1
    p = Property(**data, code=f"PR-{n:04d}", submitted_by_id=user.id, h3_9=geo.cell(body.lat, body.lng, 9),
                 data_quality=warnings, stage="submitted")
    db.add(p)
    db.flush()
    P.log(db, p, user, "created", f"Onboarded by {user.name}", {"warnings": warnings})
    if p.mission_id:
        m = db.get(ScoutMission, p.mission_id)
        if m and m.status == "open":
            m.status = "in_progress"
    notify(db, role_users(db, "bd_manager"), "property", f"New property {p.code}: {p.title}",
           f"Submitted by {user.name} in {p.locality or 'Chennai'}", f"/properties/{p.id}")
    db.commit()
    new_evaluation(db, p, "onboarding")
    return {"property": property_full(p), "duplicate_submit": False}


@router.post("/properties/{pid}/photos", status_code=201)
async def upload_photo(pid: int, file: UploadFile = File(...), caption: str | None = Form(None),
                       db: Session = Depends(get_db), user: User = Depends(require("bd_exec", "bd_manager"))):
    p = db.get(Property, pid)
    if not p:
        raise HTTPException(404, "Property not found")
    if user.role == "bd_exec" and p.submitted_by_id != user.id:
        raise HTTPException(403, "You can only add photos to your own properties")
    # raster only: user-uploaded SVG could carry script
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(415, "Please upload a JPEG, PNG or WebP photo")
    content = await file.read()
    if len(content) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Photo too large (max 8 MB)")
    ext = {"image/png": ".png", "image/webp": ".webp"}.get(file.content_type, ".jpg")
    rel = Path("properties") / str(pid) / f"{uuid.uuid4().hex[:12]}{ext}"
    dest = get_settings().upload_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    ph = PropertyPhoto(property_id=pid, path=rel.as_posix(), caption=caption)
    db.add(ph)
    db.commit()
    return {"id": ph.id, "url": f"/uploads/{ph.path}", "caption": caption}


@router.get("/properties")
def list_properties(stage: str | None = None, mine: bool = False, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    q = select(Property).order_by(Property.id.desc())
    if user.role == "bd_exec" or mine:
        q = q.where(Property.submitted_by_id == user.id)
    if stage:
        q = q.where(Property.stage.in_(stage.split(",")))
    return [property_summary(p) for p in db.scalars(q)]


def _get(db: Session, pid: int, user: User) -> Property:
    p = db.get(Property, pid)
    if not p:
        raise HTTPException(404, "Property not found")
    if user.role == "bd_exec" and p.submitted_by_id != user.id:
        raise HTTPException(404, "Property not found")
    return p


@router.get("/properties/{pid}")
def get_property(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    evals = list(db.scalars(select(PropertyEvaluation).where(PropertyEvaluation.property_id == pid)
                            .order_by(PropertyEvaluation.version.desc())))
    events = list(db.scalars(select(PropertyEvent).where(PropertyEvent.property_id == pid).order_by(PropertyEvent.id.desc())))
    studies = [s for s in db.scalars(select(CatchmentStudy)) if s.property_id == pid or p.h3_9 in set(s.requested_cells)]
    done = next((e for e in evals if e.status == "completed"), None)
    pending = evals[0] if evals and evals[0].status != "completed" else None
    return {**property_full(p), "evaluation": evaluation_dict(db, done),
            "pending_evaluation": evaluation_dict(db, pending),
            "evaluations": [{"version": e.version, "trigger": e.trigger, "score": e.score, "status": e.status,
                             "recommendation": e.recommendation, "created_at": e.created_at.isoformat() + "Z"} for e in evals],
            "events": [event_dict(e) for e in events], "allowed_transitions": P.allowed_next(p, user),
            "studies": [study_summary(s) for s in studies],
            "duplicates": find_duplicates(db, p.lat, p.lng, exclude_id=p.id)}


class PropertyPatch(BaseModel):
    note: str | None = None
    fields: dict


@router.patch("/properties/{pid}")
def update_property(pid: int, body: PropertyPatch, db: Session = Depends(get_db),
                    user: User = Depends(require("bd_exec", "bd_manager"))):
    p = _get(db, pid, user)
    changed = {}
    allowed = set(PROPERTY_FIELDS) | {"title", "lat", "lng", "address", "locality", "pincode"}
    for k, v in body.fields.items():
        if k not in allowed:
            raise HTTPException(422, f"Field {k} cannot be edited")
        if k == "available_from" and v:
            v = date.fromisoformat(v)
        if getattr(p, k) != v:
            changed[k] = {"from": str(getattr(p, k)), "to": str(v)}
            setattr(p, k, v)
    if "lat" in changed or "lng" in changed:
        if not geo.in_chennai(p.lat, p.lng):
            raise HTTPException(422, "That pin is outside the Chennai region")
        p.h3_9 = geo.cell(p.lat, p.lng, 9)
    if not changed:
        return {"property": property_full(p), "changed": {}}
    P.log(db, p, user, "details_updated", body.note, {"changed": changed})
    if p.stage == "info_requested" and user.id == p.submitted_by_id:
        P.transition(db, p, user, "submitted", body.note or "Requested information added")
        notify(db, role_users(db, "bd_manager"), "property", f"{p.code} updated by {user.name}",
               body.note, f"/properties/{p.id}")
    db.commit()
    new_evaluation(db, p, "details_updated")
    return {"property": property_full(p), "changed": changed}


class TransitionIn(BaseModel):
    to: str
    note: str
    reason: str | None = None


@router.post("/properties/{pid}/transition")
def transition(pid: int, body: TransitionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    try:
        P.transition(db, p, user, body.to, body.note, body.reason)
    except P.TransitionError as exc:
        raise HTTPException(422, str(exc)) from exc
    if user.role == "bd_manager" and p.submitted_by_id != user.id:
        verb = {"info_requested": "needs more information", "shortlisted": "was shortlisted — please proceed",
                "rejected": "was rejected", "approved": "was approved 🎉", "site_visit": "moved to site visit",
                "negotiation": "moved to negotiation", "on_hold": "is on hold"}.get(body.to, f"moved to {body.to}")
        notify(db, [p.submitted_by_id], "property", f"{p.code} {verb}", body.note, f"/properties/{p.id}")
    elif user.role == "bd_exec":
        notify(db, role_users(db, "bd_manager"), "property", f"{p.code}: {user.name} responded", body.note,
               f"/properties/{p.id}")
    db.commit()
    return get_property(pid, db, user)


class CommentIn(BaseModel):
    note: str = Field(min_length=1)


@router.post("/properties/{pid}/comments")
def comment(pid: int, body: CommentIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    P.log(db, p, user, "comment", body.note)
    db.commit()
    return get_property(pid, db, user)


@router.post("/properties/{pid}/evaluate")
def reevaluate(pid: int, db: Session = Depends(get_db), user: User = Depends(require("bd_manager"))):
    p = _get(db, pid, user)
    last = db.scalar(select(PropertyEvaluation).where(PropertyEvaluation.property_id == pid)
                     .order_by(PropertyEvaluation.version.desc()))
    if last and last.status == "failed" and last.job_id:
        jobs.retry(db, db.get(Job, last.job_id))
        last.status = "queued"
        db.commit()
    else:
        new_evaluation(db, p, "manual")
    return get_property(pid, db, user)
