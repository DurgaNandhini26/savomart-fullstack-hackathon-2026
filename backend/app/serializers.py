"""Model -> JSON helpers (kept explicit so API shapes are obvious and stable)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from . import geo
from .auth import user_dict
from .models import (AreaReport, CatchmentStudy, Job, Property, PropertyEvaluation, PropertyEvent, ScoutMission,
                     SurveyLane, WorkUnit)
from .services.jobs import job_dict
from .services.pipeline import STAGES


def iso(v: datetime | date | None) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat() + "Z"
    return v.isoformat()


def report_summary(r: AreaReport) -> dict:
    return {"id": r.id, "name": r.name, "selection_type": r.selection_type, "selection_input": r.selection_input,
            "status": r.status, "score": r.score, "band": r.band, "confidence": r.confidence,
            "area_km2": r.area_km2, "center": [r.center_lat, r.center_lng], "n_cells": len(r.cells or []),
            "created_by": user_dict(r.created_by), "created_at": iso(r.created_at),
            "completed_at": iso(r.completed_at), "has_ground_truth": bool(r.ground_truth)}


def report_full(db: Session, r: AreaReport) -> dict:
    return {**report_summary(r), "cells": r.cells, "outline": geo.cells_outline(r.cells) if r.cells else None,
            "pillars": r.pillars, "indicators": r.indicators, "profile": r.profile, "hotspots": r.hotspots,
            "narrative": r.narrative, "data_versions": r.data_versions, "ground_truth": r.ground_truth,
            "error": r.error, "job": job_dict(db.get(Job, r.job_id)) if r.job_id else None}


def mission_dict(m: ScoutMission, n_props: int = 0) -> dict:
    return {"id": m.id, "title": m.title, "report_id": m.report_id, "report_name": m.report.name if m.report else None,
            "hotspot_rank": m.hotspot_rank, "lat": m.lat, "lng": m.lng, "radius_m": m.radius_m, "brief": m.brief,
            "assignee": user_dict(m.assignee), "created_by": user_dict(m.created_by), "status": m.status,
            "due_date": iso(m.due_date), "created_at": iso(m.created_at), "properties": n_props}


def evaluation_dict(db: Session, e: PropertyEvaluation | None) -> dict | None:
    if not e:
        return None
    return {"id": e.id, "version": e.version, "trigger": e.trigger, "status": e.status, "score": e.score,
            "recommendation": e.recommendation, "pillars": e.pillars, "facts": e.facts, "insights": e.insights,
            "risks": e.risks, "narrative": e.narrative, "catchment_study_id": e.catchment_study_id,
            "data_versions": e.data_versions, "error": e.error, "created_at": iso(e.created_at),
            "job": job_dict(db.get(Job, e.job_id)) if e.job_id else None}


PROPERTY_FIELDS = ["property_type", "carpet_area_sqft", "frontage_ft", "floor", "ceiling_height_ft", "rent_monthly",
                   "rent_negotiable", "deposit_months", "lease_years", "parking_2w", "parking_4w", "road_facing",
                   "road_width_ft", "visibility", "power_kw", "truck_access", "available_from", "owner_name",
                   "owner_phone", "notes"]


def property_summary(p: Property) -> dict:
    return {"id": p.id, "code": p.code, "title": p.title, "lat": p.lat, "lng": p.lng, "stage": p.stage,
            "stage_label": STAGES.get(p.stage, p.stage), "locality": p.locality, "pincode": p.pincode,
            "address": p.address, "property_type": p.property_type, "carpet_area_sqft": p.carpet_area_sqft,
            "rent_monthly": p.rent_monthly, "score": p.latest_score, "recommendation": p.latest_recommendation,
            "submitted_by": user_dict(p.submitted_by), "mission_id": p.mission_id,
            "photo": f"/uploads/{p.photos[0].path}" if p.photos else None, "n_photos": len(p.photos),
            "data_quality": p.data_quality or [], "duplicate_of_id": p.duplicate_of_id,
            "created_at": iso(p.created_at), "updated_at": iso(p.updated_at)}


def property_full(p: Property) -> dict:
    d = property_summary(p)
    for f in PROPERTY_FIELDS:
        v = getattr(p, f)
        d[f] = iso(v) if isinstance(v, date) else v
    d.update(gps_accuracy_m=p.gps_accuracy_m, device_lat=p.device_lat, device_lng=p.device_lng,
             photos=[{"id": ph.id, "url": f"/uploads/{ph.path}", "caption": ph.caption} for ph in p.photos],
             mission=mission_dict(p.mission) if p.mission else None)
    return d


def event_dict(e: PropertyEvent) -> dict:
    return {"id": e.id, "action": e.action, "from_stage": e.from_stage, "to_stage": e.to_stage, "note": e.note,
            "meta": e.meta, "actor": user_dict(e.actor), "created_at": iso(e.created_at)}


def lane_feature(l: SurveyLane, obs: dict | None = None, unit: WorkUnit | None = None) -> dict:
    return {"type": "Feature", "id": l.id,
            "properties": {"id": l.id, "name": l.name, "highway": l.highway, "length_m": l.length_m,
                           "status": l.status, "work_unit_id": l.work_unit_id,
                           "color": unit.color if unit else None, "observation": obs},
            "geometry": {"type": "MultiLineString", "coordinates": l.coords}}


def unit_dict(u: WorkUnit, with_geo: bool = True) -> dict:
    done = [l for l in u.lanes if l.status != "pending"]
    d = {"id": u.id, "study_id": u.study_id, "name": u.name, "color": u.color, "assignee": user_dict(u.assignee),
         "status": u.status, "lane_count": u.lane_count, "lane_km": round(u.lane_m / 1000, 2),
         "lanes_done": len(done), "km_done": round(sum(l.length_m for l in done) / 1000, 2),
         "due_date": iso(u.due_date), "n_cells": len(u.cells)}
    if with_geo:
        d["outline"] = geo.cells_outline(u.cells)
    return d


def study_summary(s: CatchmentStudy) -> dict:
    lanes = [l for u in s.work_units for l in u.lanes]
    total = sum(l.length_m for l in lanes)
    done = sum(l.length_m for l in lanes if l.status != "pending")
    return {"id": s.id, "code": s.code, "title": s.title, "target_type": s.target_type,
            "property_id": s.property_id, "report_id": s.report_id, "status": s.status, "priority": s.priority,
            "center": [s.center_lat, s.center_lng], "radius_m": s.radius_m,
            "n_cells": len(s.cells), "n_requested_cells": len(s.requested_cells),
            "reused": [{k: v for k, v in r.items() if k != "cells"} | {"n_cells": len(r.get("cells", []))}
                       for r in (s.reused or [])],
            "requested_by": user_dict(s.requested_by), "due_date": iso(s.due_date), "notes": s.notes,
            "units": len(s.work_units), "progress": round(done / total, 2) if total else 0,
            "lane_km": round(total / 1000, 2), "created_at": iso(s.created_at), "completed_at": iso(s.completed_at),
            "has_insights": bool(s.insights)}
