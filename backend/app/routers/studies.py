"""M3 — catchment study requests, planning, field capture and roll-up."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import geo
from ..auth import current_user, require
from ..db import get_db
from ..models import (AreaReport, CatchmentStudy, LaneObservation, Property, SurveyLane, User, WorkUnit, utcnow)
from ..serializers import iso, lane_feature, study_summary, unit_dict
from ..services import catchment as C
from ..services import pipeline as P
from ..services.notify import notify, role_users
from ..services.property_eval import ground_truth_for, new_evaluation

router = APIRouter(prefix="/api")


class StudyTarget(BaseModel):
    target_type: str = Field(pattern="^(property|area)$")
    property_id: int | None = None
    report_id: int | None = None
    radius_m: int = Field(800, ge=300, le=2000)


class StudyIn(StudyTarget):
    priority: str = Field("normal", pattern="^(low|normal|high)$")
    due_date: date | None = None
    notes: str | None = None


def _target(db: Session, body: StudyTarget) -> dict:
    if body.target_type == "property":
        p = db.get(Property, body.property_id or 0)
        if not p:
            raise HTTPException(422, "Pick a property")
        cells = geo.disk_cells(p.lat, p.lng, body.radius_m, 9)
        return {"cells": cells, "lat": p.lat, "lng": p.lng, "title": f"{p.code} · {p.title}", "property": p,
                "radius": body.radius_m}
    r = db.get(AreaReport, body.report_id or 0)
    if not r or r.status != "completed":
        raise HTTPException(422, "Pick a completed area report")
    cells = geo.children(r.cells, 9)
    if len(cells) > 400:
        raise HTTPException(422, "Area too large for one catchment study (max ~40 km²); analyse a smaller area.")
    return {"cells": cells, "lat": r.center_lat, "lng": r.center_lng, "title": r.name, "report": r, "radius": None}


@router.post("/studies/preview")
def preview(body: StudyTarget, db: Session = Depends(get_db), _: User = Depends(require("bd_manager"))):
    t = _target(db, body)
    plan = C.plan_reuse(db, t["cells"])
    weights = C.lane_weights(db, plan["remaining_cells"])
    return {**{k: v for k, v in plan.items()}, "requested": len(t["cells"]),
            "lane_km_to_survey": round(sum(weights.values()) / 1000, 1),
            "geojson": geo.cells_to_feature_collection(
                t["cells"], {c: {"covered": c in set(plan["covered_cells"])} for c in t["cells"]})}


@router.post("/studies", status_code=201)
def create_study(body: StudyIn, db: Session = Depends(get_db), user: User = Depends(require("bd_manager"))):
    t = _target(db, body)
    plan = C.plan_reuse(db, t["cells"])
    n = (db.scalar(select(func.max(CatchmentStudy.id))) or 0) + 1
    st = CatchmentStudy(
        code=f"CS-{n:03d}", target_type=body.target_type, property_id=body.property_id if body.target_type == "property" else None,
        report_id=body.report_id if body.target_type == "area" else None, title=t["title"][:200],
        center_lat=t["lat"], center_lng=t["lng"], radius_m=t["radius"],
        requested_cells=t["cells"], cells=[] if plan["fully_reused"] else plan["remaining_cells"],
        reused=[{"study_id": s["study_id"], "code": s["code"], "cells": s["cells"], "status": s["status"]}
                for s in plan["sources"]],
        status="reused" if plan["fully_reused"] else "requested", priority=body.priority, due_date=body.due_date,
        notes=body.notes, requested_by_id=user.id)
    db.add(st)
    db.flush()
    prop = t.get("property")
    if prop and "catchment_study" in P.allowed_next(prop, user):
        P.transition(db, prop, user, "catchment_study", f"Catchment study {st.code} requested"
                     + (" (satisfied by existing survey data)" if plan["fully_reused"] else ""))
    elif prop:
        P.log(db, prop, user, "catchment_requested", f"Catchment study {st.code} requested")
    if plan["fully_reused"]:
        sources_done = all(db.get(CatchmentStudy, s["study_id"]).status == "completed" for s in plan["sources"])
        if sources_done:
            finalize(db, st)
        notify(db, [user.id], "study", f"{st.code} reuses existing survey data ({round(plan['coverage'] * 100)}% covered)",
               "No new fieldwork needed." if sources_done else "Waiting for the overlapping survey to finish.",
               f"/studies/{st.id}")
    else:
        notify(db, role_users(db, "survey_manager"), "study", f"New catchment study request {st.code}",
               f"{st.title} · priority {st.priority}", f"/studies/{st.id}")
    db.commit()
    return study_summary(st)


@router.get("/studies")
def list_studies(db: Session = Depends(get_db), _: User = Depends(require("bd_manager", "survey_manager"))):
    return [study_summary(s) for s in db.scalars(select(CatchmentStudy).order_by(CatchmentStudy.id.desc()))]


@router.get("/studies/{sid}")
def get_study(sid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    st = db.get(CatchmentStudy, sid)
    if not st:
        raise HTTPException(404, "Study not found")
    if user.role == "survey_exec" and not any(u.assignee_id == user.id for u in st.work_units):
        raise HTTPException(404, "Study not found")
    lanes = list(db.scalars(select(SurveyLane).where(SurveyLane.study_id == sid)))
    obs = C.latest_observations(db, [l.id for l in lanes])
    units = {u.id: u for u in st.work_units}
    weights = C.lane_weights(db, st.cells) if st.status == "requested" else {}
    return {
        **study_summary(st),
        "requested_geojson": geo.cells_to_feature_collection(
            st.requested_cells, {c: {"covered": c not in set(st.cells)} for c in st.requested_cells}),
        "units": [unit_dict(u) for u in st.work_units],
        "lanes": {"type": "FeatureCollection", "features": [
            lane_feature(l, obs[l.id].data if l.id in obs else None, units.get(l.work_unit_id)) for l in lanes]},
        "insights": st.insights,
        "suggested_units": C.suggest_units(sum(weights.values()), len(role_users(db, "survey_exec"))) if weights else None,
        "lane_km_estimate": round(sum(weights.values()) / 1000, 1) if weights else None,
        "surveyors": len(role_users(db, "survey_exec")), "lane_km_per_day": C.LANE_KM_PER_DAY,
        "property": {"id": st.property.id, "code": st.property.code, "title": st.property.title,
                     "lat": st.property.lat, "lng": st.property.lng} if st.property else None,
        "report": {"id": st.report.id, "name": st.report.name} if st.report else None,
        "progress_detail": C.progress(db, st),
    }


class PlanIn(BaseModel):
    units: int = Field(ge=1, le=8)


@router.post("/studies/{sid}/plan")
def plan(sid: int, body: PlanIn, db: Session = Depends(get_db), user: User = Depends(require("survey_manager"))):
    st = db.get(CatchmentStudy, sid)
    if not st or st.status not in ("requested", "planned"):
        raise HTTPException(409, "Only new or planned studies can be (re)split")
    try:
        C.plan_work(db, st, body.units)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    db.refresh(st)
    return get_study(sid, db, user)


class AssignIn(BaseModel):
    assignee_id: int
    due_date: date | None = None


@router.post("/work-units/{uid}/assign")
def assign(uid: int, body: AssignIn, db: Session = Depends(get_db), user: User = Depends(require("survey_manager"))):
    u = db.get(WorkUnit, uid)
    ex = db.get(User, body.assignee_id)
    if not u:
        raise HTTPException(404, "Work unit not found")
    if not ex or ex.role != "survey_exec":
        raise HTTPException(422, "Assign to a survey executive")
    u.assignee_id, u.due_date = ex.id, body.due_date
    if u.status == "unassigned":
        u.status = "assigned"
    st = u.study
    notify(db, [ex.id], "assignment", f"New survey assignment: {st.code} {u.name}",
           f"{u.lane_count} lanes · {round(u.lane_m / 1000, 1)} km", f"/survey/{u.id}")
    db.commit()
    return unit_dict(u)


@router.get("/my/assignments")
def my_assignments(db: Session = Depends(get_db), user: User = Depends(require("survey_exec"))):
    units = list(db.scalars(select(WorkUnit).where(WorkUnit.assignee_id == user.id).order_by(WorkUnit.id.desc())))
    return [{**unit_dict(u, with_geo=False), "study": {"id": u.study.id, "code": u.study.code, "title": u.study.title,
                                                        "priority": u.study.priority}} for u in units]


@router.get("/work-units/{uid}")
def get_unit(uid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    u = db.get(WorkUnit, uid)
    if not u or (user.role == "survey_exec" and u.assignee_id != user.id):
        raise HTTPException(404, "Assignment not found")
    obs = C.latest_observations(db, [l.id for l in u.lanes])
    return {**unit_dict(u), "study": study_summary(u.study),
            "lanes": {"type": "FeatureCollection",
                      "features": [lane_feature(l, obs[l.id].data if l.id in obs else None, u) for l in u.lanes]}}


class ObservationIn(BaseModel):
    client_uuid: str = Field(min_length=8, max_length=40)
    lane_id: int
    captured_at: datetime
    data: dict


class ObservationBatch(BaseModel):
    observations: list[ObservationIn] = Field(max_length=500)


OBS_SCHEMA = {"households": int, "kiranas": int, "supermarkets": int}


def _validate_obs(d: dict) -> dict:
    status = d.get("status", "done")
    if status not in ("done", "inaccessible"):
        raise ValueError("status must be done or inaccessible")
    out = {"status": status}
    for k, t in OBS_SCHEMA.items():
        if d.get(k) not in (None, ""):
            v = t(d[k])
            if v < 0 or v > 5000:
                raise ValueError(f"{k} out of range")
            out[k] = v
    for k, allowed in {"housing_type": {"independent", "apartments", "gated", "mixed", "informal", "commercial"},
                       "sec": {"A", "B", "C", "D"}, "footfall": {"low", "medium", "high"},
                       "access": {"car", "two_wheeler", "walk_only"}, "occupancy": {"high", "medium", "low"}}.items():
        if d.get(k):
            if d[k] not in allowed:
                raise ValueError(f"{k} invalid")
            out[k] = d[k]
    out["competitor_brands"] = [str(b)[:40] for b in (d.get("competitor_brands") or [])][:12]
    out["notes"] = str(d.get("notes") or "")[:1000]
    return out


@router.post("/survey/observations")
def sync_observations(body: ObservationBatch, db: Session = Depends(get_db), user: User = Depends(require("survey_exec"))):
    """Idempotent batch sync from the offline outbox. Same client_uuid twice = no-op."""
    results, touched = [], set()
    for ob in body.observations:
        if db.scalar(select(LaneObservation).where(LaneObservation.client_uuid == ob.client_uuid)):
            results.append({"client_uuid": ob.client_uuid, "status": "duplicate"})
            continue
        lane = db.get(SurveyLane, ob.lane_id)
        if not lane or not lane.work_unit or lane.work_unit.assignee_id != user.id:
            results.append({"client_uuid": ob.client_uuid, "status": "rejected", "error": "Lane not assigned to you"})
            continue
        try:
            data = _validate_obs(ob.data)
        except (ValueError, TypeError) as exc:
            results.append({"client_uuid": ob.client_uuid, "status": "rejected", "error": str(exc)})
            continue
        captured = ob.captured_at.replace(tzinfo=None)
        db.add(LaneObservation(lane_id=lane.id, client_uuid=ob.client_uuid, surveyor_id=user.id, data=data,
                               captured_at=captured))
        lane.status = data["status"]
        u = lane.work_unit
        if u.status in ("assigned", "unassigned"):
            u.status = "in_progress"
        if u.study.status == "planned":
            u.study.status = "in_progress"
        touched.add(u.id)
        results.append({"client_uuid": ob.client_uuid, "status": "accepted"})
    db.flush()
    completed = []
    for uid in touched:
        u = db.get(WorkUnit, uid)
        if u.lanes and all(l.status != "pending" for l in u.lanes):
            u.status = "done"
            notify(db, role_users(db, "survey_manager"), "assignment", f"{u.study.code} {u.name} completed by {user.name}",
                   None, f"/studies/{u.study_id}")
        st = u.study
        if st.status == "in_progress" and st.work_units and all(w.status == "done" for w in st.work_units):
            finalize(db, st)
            completed.append(st.code)
    db.commit()
    return {"results": results, "studies_completed": completed}


@router.post("/studies/{sid}/complete")
def force_complete(sid: int, db: Session = Depends(get_db), _: User = Depends(require("survey_manager"))):
    """Close a study early (e.g. last lanes inaccessible) once enough has been covered."""
    st = db.get(CatchmentStudy, sid)
    if not st or st.status not in ("in_progress", "planned"):
        raise HTTPException(409, "Study is not in progress")
    pr = C.progress(db, st)
    if pr["pct"] < 0.6:
        raise HTTPException(409, f"Only {round(pr['pct'] * 100)}% of lane-km surveyed; need at least 60% to close early.")
    finalize(db, st)
    db.commit()
    return study_summary(st)


def finalize(db: Session, st: CatchmentStudy) -> None:
    """Roll up insights, link them back to the property/area and re-evaluate affected properties."""
    st.insights = C.rollup(db, st)
    if st.status != "reused":
        st.status = "completed"
    st.completed_at = utcnow()
    for u in st.work_units:
        if u.status != "done":
            u.status = "done"
    db.flush()
    _propagate(db, st)
    # studies that were waiting on this one (piggybacked) can now finalize too
    for other in db.scalars(select(CatchmentStudy).where(CatchmentStudy.status == "reused", CatchmentStudy.id != st.id)):
        if any(r["study_id"] == st.id for r in (other.reused or [])) and not other.insights:
            other.insights = C.rollup(db, other)
            other.completed_at = utcnow()
            _propagate(db, other)


def _propagate(db: Session, st: CatchmentStudy) -> None:
    req = set(st.requested_cells)
    if st.report_id:
        r = db.get(AreaReport, st.report_id)
        if r:
            r.ground_truth = {"study_id": st.id, "code": st.code, **(st.insights or {})}
    # only properties for which this study is now the best ground truth get re-evaluated
    affected = [p for p in db.scalars(select(Property))
                if p.h3_9 in req and p.stage not in ("rejected", "duplicate") and
                (g := ground_truth_for(db, p)) is not None and g.id == st.id]
    notify(db, [st.requested_by_id], "study", f"Catchment study {st.code} complete",
           f"{len(affected)} propert{'y' if len(affected) == 1 else 'ies'} re-evaluated with ground truth", f"/studies/{st.id}")
    db.commit()
    for p in affected:
        P.log(db, p, None, "catchment_data", f"Ground-truth data from {st.code} applied; evaluation refreshed")
        db.commit()
        new_evaluation(db, p, "catchment_study")


@router.get("/studies/{sid}/progress")
def study_progress(sid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    st = db.get(CatchmentStudy, sid)
    if not st:
        raise HTTPException(404, "Study not found")
    return {**C.progress(db, st), "status": st.status, "updated": iso(utcnow())}


@router.get("/team")
def team(db: Session = Depends(get_db), _: User = Depends(require("survey_manager"))):
    """Survey executives' current workload, so the manager can split work fairly."""
    out = []
    for ex in role_users(db, "survey_exec"):
        units = list(db.scalars(select(WorkUnit).where(WorkUnit.assignee_id == ex.id)))
        active = [u for u in units if u.status != "done"]
        lanes = [l for u in active for l in u.lanes]
        left_m = sum(l.length_m for l in lanes if l.status == "pending")
        out.append({"user": {"id": ex.id, "name": ex.name, "phone": ex.phone},
                    "active_units": [{"id": u.id, "name": u.name, "study": u.study.code, "status": u.status} for u in active],
                    "done_units": len(units) - len(active), "lanes_left": sum(1 for l in lanes if l.status == "pending"),
                    "km_left": round(left_m / 1000, 1), "days_left": round(left_m / 1000 / C.LANE_KM_PER_DAY, 1)})
    return out
