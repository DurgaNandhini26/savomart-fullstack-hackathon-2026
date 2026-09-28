"""M1 area reports + scouting missions (the hand-off from M1 to M2)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import geo
from ..auth import current_user, require
from ..db import get_db
from ..models import AreaReport, Job, Property, ScoutMission, User
from ..serializers import mission_dict, report_full, report_summary
from ..services import areas as A
from ..services import jobs
from ..services.notify import notify

router = APIRouter(prefix="/api")
manager = require("bd_manager")


class ReportIn(BaseModel):
    selection_type: str = Field(pattern="^(pincode|locality|cells)$")
    value: str | None = None
    cells: list[str] | None = None
    name: str | None = None


@router.post("/reports", status_code=201)
def create_report(body: ReportIn, db: Session = Depends(get_db), user: User = Depends(manager)):
    try:
        res = A.resolve(db, body.selection_type, body.value, body.cells)
    except A.AreaError as exc:
        raise HTTPException(422, str(exc)) from exc
    lat, lng = geo.centroid_of_cells(res["cells"])
    rep = AreaReport(name=(body.name or res["name"])[:200], selection_type=body.selection_type,
                     selection_input=res["input"], cells=res["cells"], center_lat=lat, center_lng=lng,
                     area_km2=round(geo.cells_area_km2(res["cells"]), 2), status="queued", created_by_id=user.id)
    db.add(rep)
    db.commit()
    job = jobs.enqueue(db, "area_analysis", rep.id)
    rep.job_id = job.id
    db.commit()
    return report_full(db, rep)


@router.get("/reports")
def list_reports(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [report_summary(r) for r in db.scalars(select(AreaReport).order_by(AreaReport.id.desc()))]


@router.get("/reports/{rid}")
def get_report(rid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    r = db.get(AreaReport, rid)
    if not r:
        raise HTTPException(404, "Report not found")
    out = report_full(db, r)
    out["missions"] = [mission_dict(m) for m in db.scalars(select(ScoutMission).where(ScoutMission.report_id == rid))]
    return out


@router.post("/reports/{rid}/retry")
def retry_report(rid: int, db: Session = Depends(get_db), _: User = Depends(manager)):
    r = db.get(AreaReport, rid)
    if not r or not r.job_id:
        raise HTTPException(404, "Report not found")
    job = db.get(Job, r.job_id)
    if job.status not in ("failed",):
        raise HTTPException(409, "Only failed analyses can be retried")
    r.status, r.error = "queued", None
    jobs.retry(db, job)
    return report_full(db, r)


@router.post("/reports/{rid}/rerun", status_code=201)
def rerun_report(rid: int, db: Session = Depends(get_db), user: User = Depends(manager)):
    """Re-analyse the same area against the current data — a new, separately timestamped report."""
    r = db.get(AreaReport, rid)
    if not r:
        raise HTTPException(404, "Report not found")
    return create_report(ReportIn(selection_type="cells", cells=r.cells, name=r.name), db, user)


@router.get("/reports-compare")
def compare(ids: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    out = []
    for i in ids.split(",")[:4]:
        r = db.get(AreaReport, int(i))
        if r:
            out.append(report_full(db, r))
    return out


# ------------------------------------------------------------------ missions

class MissionIn(BaseModel):
    title: str
    assignee_id: int
    lat: float
    lng: float
    radius_m: int = 600
    report_id: int | None = None
    hotspot_rank: int | None = None
    brief: str | None = None
    due_date: date | None = None


@router.post("/missions", status_code=201)
def create_mission(body: MissionIn, db: Session = Depends(get_db), user: User = Depends(manager)):
    ex = db.get(User, body.assignee_id)
    if not ex or ex.role != "bd_exec":
        raise HTTPException(422, "Missions can only be assigned to BD executives")
    if not geo.in_chennai(body.lat, body.lng):
        raise HTTPException(422, "Mission location is outside the Chennai region")
    m = ScoutMission(**body.model_dump(), created_by_id=user.id)
    db.add(m)
    db.flush()
    notify(db, [ex.id], "mission", f"New scouting mission: {m.title}", body.brief, f"/missions/{m.id}")
    db.commit()
    return mission_dict(m)


@router.get("/missions")
def list_missions(db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(ScoutMission).order_by(ScoutMission.id.desc())
    if user.role == "bd_exec":
        q = q.where(ScoutMission.assignee_id == user.id)
    counts = dict(db.execute(select(Property.mission_id, func.count()).group_by(Property.mission_id)).all())
    return [mission_dict(m, counts.get(m.id, 0)) for m in db.scalars(q)]


@router.get("/missions/{mid}")
def get_mission(mid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = db.get(ScoutMission, mid)
    if not m or (user.role == "bd_exec" and m.assignee_id != user.id):
        raise HTTPException(404, "Mission not found")
    from ..serializers import property_summary
    props = list(db.scalars(select(Property).where(Property.mission_id == mid)))
    hotspot = None
    if m.report and m.hotspot_rank:
        hotspot = next((h for h in (m.report.hotspots or []) if h["rank"] == m.hotspot_rank), None)
    return {**mission_dict(m, len(props)), "properties": [property_summary(p) for p in props], "hotspot": hotspot}


class MissionPatch(BaseModel):
    status: str = Field(pattern="^(open|in_progress|done|cancelled)$")


@router.patch("/missions/{mid}")
def update_mission(mid: int, body: MissionPatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = db.get(ScoutMission, mid)
    if not m:
        raise HTTPException(404, "Mission not found")
    if user.role == "bd_exec" and (m.assignee_id != user.id or body.status == "cancelled"):
        raise HTTPException(403, "Not your mission")
    if user.role not in ("bd_exec", "bd_manager"):
        raise HTTPException(403, "Not allowed")
    m.status = body.status
    if user.role == "bd_exec" and body.status == "done":
        notify(db, [m.created_by_id], "mission", f"{user.name} finished mission: {m.title}", None, f"/missions/{m.id}")
    db.commit()
    return mission_dict(m)
