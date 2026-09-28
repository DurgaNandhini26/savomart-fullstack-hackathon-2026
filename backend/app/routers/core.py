"""Auth, reference data, map layers, notifications and dashboards."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import geo
from ..auth import current_user, make_token, user_dict, verify_password
from ..config import get_settings
from ..db import get_db
from ..llm import provider_info
from ..models import (AreaReport, CatchmentStudy, Notification, OpportunityCell, Property, ScoutMission, Store,
                      User, WorkUnit)
from ..serializers import iso
from ..services import areas as A
from ..services import features as F
from ..services.analysis import data_versions
from ..services.pipeline import REJECT_REASONS, STAGES, TRANSITIONS
from ..services.scoring import PILLARS

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------ auth

class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(func.lower(User.username) == body.username.lower().strip()))
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Wrong username or password")
    return {"token": make_token(u), "user": user_dict(u)}


@router.get("/auth/demo-users")
def demo_users(db: Session = Depends(get_db)):
    """Public list for the login screen's one-tap role switcher (demo only)."""
    return [user_dict(u) for u in db.scalars(select(User).where(User.active.is_(True)).order_by(User.id))]


@router.post("/auth/switch/{user_id}")
def switch(user_id: int, db: Session = Depends(get_db)):
    """Demo role switcher — issue a token for a seeded user without a password."""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "No such user")
    return {"token": make_token(u), "user": user_dict(u)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_dict(user)


@router.get("/users")
def users(role: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(User).where(User.active.is_(True))
    if role:
        q = q.where(User.role == role)
    return [user_dict(u) for u in db.scalars(q.order_by(User.name))]


# ------------------------------------------------------------------ reference

@router.get("/meta")
def meta(db: Session = Depends(get_db), _: User = Depends(current_user)):
    s = get_settings()
    return {
        "app": s.app_name, "llm": provider_info(), "data_versions": data_versions(db),
        "stages": STAGES, "transitions": TRANSITIONS, "reject_reasons": REJECT_REASONS,
        "pillars": {k: {"weight": w, "label": l, "description": d} for k, (w, l, d) in PILLARS.items()},
        "bbox": geo.CHENNAI_BBOX, "center": geo.CHENNAI_CENTER,
        "reuse_policy": {"min_coverage": s.reuse_min_coverage, "max_age_days": s.reuse_max_age_days},
    }


@router.get("/geo/stores")
def stores(zone: str | None = "CHN", db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(Store)
    if zone:
        q = q.where(Store.zone == zone)
    return [{"code": s.store_code, "name": s.name, "address": s.address, "lat": s.lat, "lng": s.lng, "zone": s.zone}
            for s in db.scalars(q)]


@router.get("/geo/search")
def search(q: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return A.search(db, q)


@router.get("/geo/resolve")
def resolve(selection_type: str, value: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Preview which grid cells a pincode / locality maps to before running an analysis."""
    try:
        res = A.resolve(db, selection_type, value, None)
    except A.AreaError as exc:
        raise HTTPException(422, str(exc)) from exc
    lat, lng = geo.centroid_of_cells(res["cells"])
    return {**res, "center": [lat, lng], "area_km2": round(geo.cells_area_km2(res["cells"]), 2),
            "geojson": geo.cells_to_feature_collection(res["cells"])}


@router.get("/geo/grid")
def grid(south: float, west: float, north: float, east: float, db: Session = Depends(get_db),
         _: User = Depends(current_user)):
    """Res-8 grid cells in the viewport, with opportunity scores where available."""
    if (north - south) * (east - west) > 0.06:
        raise HTTPException(422, "Zoom in to pick grid cells")
    cells = geo.cells_in_bbox(south, west, north, east, geo.RES_AREA)
    opp = {o.h3_8: o for o in db.scalars(select(OpportunityCell).where(OpportunityCell.h3_8.in_(cells[:900])))}
    props = {c: {"score": opp[c].score if c in opp else None,
                 "locality": opp[c].locality if c in opp else None} for c in cells}
    return geo.cells_to_feature_collection(cells, props)


@router.get("/geo/opportunity")
def opportunity(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """City-wide opportunity map; flags cells that are already covered by a report or property."""
    scouted = set()
    for r in db.scalars(select(AreaReport).where(AreaReport.status == "completed")):
        scouted.update(r.cells or [])
    for lat, lng in db.execute(select(Property.lat, Property.lng)):
        scouted.add(geo.cell(lat, lng, geo.RES_AREA))
    feats = []
    for o in db.scalars(select(OpportunityCell)):
        feats.append({"type": "Feature", "id": o.h3_8,
                      "properties": {"h3": o.h3_8, "score": o.score, "locality": o.locality,
                                     "scouted": o.h3_8 in scouted, **o.features,
                                     **{f"p_{k}": v for k, v in o.pillars.items()}},
                      "geometry": {"type": "Polygon", "coordinates": [geo.cell_boundary_geojson(o.h3_8)]}})
    return {"type": "FeatureCollection", "features": feats}


@router.get("/geo/opportunity/top")
def opportunity_top(limit: int = 15, unscouted: bool = True, db: Session = Depends(get_db),
                    _: User = Depends(current_user)):
    fc = opportunity(db, _)
    rows = [f["properties"] for f in fc["features"] if not (unscouted and f["properties"]["scouted"])]
    rows.sort(key=lambda r: -r["score"])
    # one pick per locality, so the list isn't five hexes of the same neighbourhood
    out, seen = [], set()
    for r in rows:
        if r["locality"] in seen:
            continue
        seen.add(r["locality"])
        lat, lng = geo.cell_center(r["h3"])
        out.append({**r, "lat": lat, "lng": lng})
        if len(out) >= limit:
            break
    return out


@router.get("/geo/reverse")
def reverse(lat: float, lng: float, db: Session = Depends(get_db), _: User = Depends(current_user)):
    s = get_settings()
    out = {"locality": A.nearest_locality(db, lat, lng), "address": None, "pincode": None,
           "in_region": geo.in_chennai(lat, lng), "road": F.nearest_road(db, lat, lng)}
    if s.enable_reverse_geocode:
        try:
            r = httpx.get(f"{s.nominatim_url}/reverse", timeout=6, headers={"User-Agent": s.nominatim_user_agent},
                          params={"lat": lat, "lon": lng, "format": "json", "zoom": 18, "addressdetails": 1})
            r.raise_for_status()
            j = r.json()
            out["address"] = j.get("display_name")
            out["pincode"] = (j.get("address") or {}).get("postcode")
        except Exception:  # noqa: BLE001 — reverse geocoding is a convenience, never a blocker
            pass
    return out


@router.get("/geo/pois")
def pois(lat: float, lng: float, radius: int = Query(800, le=3000), categories: str | None = None,
         db: Session = Depends(get_db), _: User = Depends(current_user)):
    cats = categories.split(",") if categories else None
    return F.pois_near(db, lat, lng, radius, cats, 500)


# ------------------------------------------------------------------ notifications

@router.get("/notifications")
def notifications(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = list(db.scalars(select(Notification).where(Notification.user_id == user.id)
                           .order_by(Notification.id.desc()).limit(50)))
    return {"unread": sum(1 for n in rows if not n.read),
            "items": [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
                       "read": n.read, "created_at": iso(n.created_at)} for n in rows]}


@router.post("/notifications/read")
def mark_read(db: Session = Depends(get_db), user: User = Depends(current_user)):
    for n in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.read.is_(False))):
        n.read = True
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ dashboards

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    out: dict = {"role": user.role}
    if user.role == "bd_manager":
        stage_counts = dict(db.execute(select(Property.stage, func.count()).group_by(Property.stage)).all())
        out.update(
            reports=db.scalar(select(func.count()).select_from(AreaReport)),
            reports_running=db.scalar(select(func.count()).select_from(AreaReport).where(AreaReport.status.in_(["queued", "running"]))),
            properties_by_stage=stage_counts,
            awaiting_review=stage_counts.get("submitted", 0),
            open_missions=db.scalar(select(func.count()).select_from(ScoutMission).where(ScoutMission.status.in_(["open", "in_progress"]))),
            studies_active=db.scalar(select(func.count()).select_from(CatchmentStudy).where(CatchmentStudy.status.in_(["requested", "planned", "in_progress"]))),
        )
    elif user.role == "bd_exec":
        out.update(
            missions_open=db.scalar(select(func.count()).select_from(ScoutMission).where(ScoutMission.assignee_id == user.id, ScoutMission.status.in_(["open", "in_progress"]))),
            my_properties=db.scalar(select(func.count()).select_from(Property).where(Property.submitted_by_id == user.id)),
            info_requested=db.scalar(select(func.count()).select_from(Property).where(Property.submitted_by_id == user.id, Property.stage == "info_requested")),
        )
    elif user.role == "survey_manager":
        out.update(
            new_requests=db.scalar(select(func.count()).select_from(CatchmentStudy).where(CatchmentStudy.status == "requested")),
            in_progress=db.scalar(select(func.count()).select_from(CatchmentStudy).where(CatchmentStudy.status.in_(["planned", "in_progress"]))),
            completed=db.scalar(select(func.count()).select_from(CatchmentStudy).where(CatchmentStudy.status.in_(["completed", "reused"]))),
            unassigned_units=db.scalar(select(func.count()).select_from(WorkUnit).where(WorkUnit.status == "unassigned")),
        )
    else:
        units = list(db.scalars(select(WorkUnit).where(WorkUnit.assignee_id == user.id)))
        out.update(assignments=len([u for u in units if u.status != "done"]),
                   lanes_left=sum(1 for u in units for l in u.lanes if l.status == "pending"))
    return out

