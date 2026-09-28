"""M3 — catchment studies: reuse, fair work splitting, lane capture roll-up.

Coverage unit = H3 res-9 cell (~0.1 km², ~350 m across). Cells never overlap, so
"what has already been surveyed" is a simple set operation.

Reuse policy (configurable):
  * a previous study's cells count as covered if it is completed within REUSE_MAX_AGE_DAYS,
    or is still planned / in progress (we piggyback instead of sending a second team);
  * if covered cells >= REUSE_MIN_COVERAGE of the new catchment, nothing new is surveyed —
    the request is satisfied by reuse; otherwise only the *uncovered* cells are surveyed.

Fair splitting: each cell is weighted by the length of lanes inside it (walking effort).
Cells are ordered by bearing around the catchment centre and cut into k contiguous
sectors of ~equal lane-km — non-overlapping by construction, compact, and each sector
starts at the centre so every surveyor has a short commute to their first lane.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import timedelta

import h3
from sqlalchemy import select
from shapely.geometry import Polygon, mapping, shape
from sqlalchemy.orm import Session

from .. import geo
from ..config import get_settings
from ..models import CatchmentStudy, LaneObservation, Road, SurveyLane, WorkUnit, utcnow
from . import features as F

UNIT_COLORS = ["#782B90", "#E6007E", "#0091D5", "#F39200", "#009B77", "#5B5BD6", "#C0392B", "#16A085"]
LANE_KM_PER_DAY = 4.0  # a surveyor walking and recording ~4 km of lanes per day
SEC_ORDER = ["A", "B", "C", "D"]


# ------------------------------------------------------------------ reuse

def reuse_candidates(db: Session, requested: set[str], exclude_id: int | None = None) -> list[dict]:
    s = get_settings()
    fresh_after = utcnow() - timedelta(days=s.reuse_max_age_days)
    out = []
    for st in db.scalars(select(CatchmentStudy).where(CatchmentStudy.status.in_(["planned", "in_progress", "completed", "requested"]))):
        if st.id == exclude_id:
            continue
        if st.status == "completed" and (st.completed_at or st.created_at) < fresh_after:
            continue
        overlap = requested & set(st.cells)
        if overlap:
            out.append({"study_id": st.id, "code": st.code, "status": st.status, "cells": sorted(overlap),
                        "age_days": (utcnow() - (st.completed_at or st.created_at)).days})
    return out


def plan_reuse(db: Session, requested: list[str]) -> dict:
    s = get_settings()
    req = set(requested)
    cands = reuse_candidates(db, req)
    covered = set()
    for c in cands:
        covered |= set(c["cells"])
    coverage = len(covered & req) / max(len(req), 1)
    return {"coverage": round(coverage, 2), "covered_cells": sorted(covered & req),
            "remaining_cells": sorted(req - covered), "sources": cands,
            "fully_reused": coverage >= s.reuse_min_coverage, "policy": {
                "min_coverage": s.reuse_min_coverage, "max_age_days": s.reuse_max_age_days}}


# ------------------------------------------------------------------ splitting

def lane_weights(db: Session, cells: list[str]) -> dict[str, float]:
    w: dict[str, float] = defaultdict(float)
    for i in range(0, len(cells), 900):
        for c9, length in db.execute(select(Road.h3_9, Road.length_m).where(Road.h3_9.in_(cells[i:i + 900]))):
            w[c9] += length
    return w


def split_by_bearing(items: list[tuple], center: tuple[float, float], k: int) -> list[list]:
    """Angular-sweep partition into k contiguous wedges of ~equal total weight. Pure function.

    items: (key, lat, lng, weight). Sorting by compass bearing from the centre and cutting the
    cumulative weight into k equal slices gives wedges that never overlap, are contiguous, and
    all touch the centre (short commute to each surveyor's first lane).
    """
    k = max(1, min(k, len(items)))
    clat, clng = center

    def bearing(it):
        _, lat, lng, _ = it
        if geo.haversine_m(clat, clng, lat, lng) < 30:
            return -1.0
        return geo.bearing_deg(clat, clng, lat, lng)

    ordered = sorted(items, key=bearing)
    total = sum(it[3] for it in ordered) or 1.0
    target = total / k
    groups: list[list] = [[]]
    acc = 0.0
    for it in ordered:
        if acc + it[3] / 2 > target * len(groups) and len(groups) < k:
            groups.append([])
        groups[-1].append(it[0])
        acc += it[3]
    return [g for g in groups if g]


def wedge(center: tuple[float, float], b0: float, b1: float, radius_m: float) -> Polygon:
    """Pie slice from bearing b0 clockwise to b1 (degrees), as a lon/lat polygon."""
    clat, clng = center
    span = (b1 - b0) % 360 or 360
    steps = max(4, int(span / 5))
    pts = [(clng, clat)]
    for i in range(steps + 1):
        b = math.radians(b0 + span * i / steps)
        dlat = radius_m * math.cos(b) / 110540
        dlng = radius_m * math.sin(b) / (111320 * math.cos(math.radians(clat)))
        pts.append((clng + dlng, clat + dlat))
    return Polygon(pts)


def compass(b: float) -> str:
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int(((b + 22.5) % 360) // 45)]


def suggest_units(total_lane_m: float, surveyors: int) -> int:
    """One unit per available surveyor, but never units smaller than ~half a day's walking."""
    days = total_lane_m / 1000 / LANE_KM_PER_DAY
    return max(1, min(8, surveyors, math.ceil(days * 2)))


def plan_work(db: Session, st: CatchmentStudy, k: int) -> list[WorkUnit]:
    """(Re)split a study into k work units and materialise its survey lanes."""
    if any(l.status != "pending" for u in st.work_units for l in u.lanes):
        raise ValueError("Survey data has already been captured; re-splitting would orphan it.")
    for u in list(st.work_units):
        db.delete(u)
    db.query(SurveyLane).filter(SurveyLane.study_id == st.id).delete()
    db.flush()

    # Split at road-segment granularity (a segment is a street piece inside one ~0.1 km² cell),
    # weighted by length = walking effort. Cells alone are too coarse for small catchments.
    segs: list[Road] = []
    for i in range(0, len(st.cells), 900):
        segs.extend(db.scalars(select(Road).where(Road.h3_9.in_(st.cells[i:i + 900]))))
    by_id = {r.id: r for r in segs}
    groups = split_by_bearing([(r.id, r.mid_lat, r.mid_lng, r.length_m) for r in segs],
                              (st.center_lat, st.center_lng), k)
    # wedge boundaries sit halfway between neighbouring groups' outermost segments
    center = (st.center_lat, st.center_lng)

    def brg(r: Road) -> float | None:
        if geo.haversine_m(st.center_lat, st.center_lng, r.mid_lat, r.mid_lng) < 30:
            return None
        return geo.bearing_deg(st.center_lat, st.center_lng, r.mid_lat, r.mid_lng)

    spans = []
    for g in groups:
        bs = [b for b in (brg(by_id[x]) for x in g) if b is not None]
        spans.append((bs[0], bs[-1]) if bs else (0.0, 0.0))
    cuts = []
    for i in range(len(groups)):
        prev_end = spans[i - 1][1]
        start = spans[i][0]
        cuts.append((prev_end + ((start - prev_end) % 360) / 2) % 360)
    area = shape(geo.cells_outline(st.cells)).buffer(0)  # only the part actually being surveyed
    radius = max((geo.haversine_m(st.center_lat, st.center_lng, r.mid_lat, r.mid_lng) for r in segs), default=500) * 1.6 + 200
    units = []
    for i, g in enumerate(groups):
        rs = [by_id[x] for x in g]
        span = f"{compass(spans[i][0])}–{compass(spans[i][1])}"
        if len(groups) == 1:
            outline = area
        else:
            outline = wedge(center, cuts[i], cuts[(i + 1) % len(groups)], radius).intersection(area)
        u = WorkUnit(study_id=st.id, name=f"Sector {chr(65 + i)} ({span})", color=UNIT_COLORS[i % len(UNIT_COLORS)],
                     cells=sorted({r.h3_9 for r in rs}), outline=mapping(outline) if not outline.is_empty else None,
                     status="unassigned")
        db.add(u)
        db.flush()
        # one lane = one OSM street within one work unit (its segments merged)
        by_way: dict[int, list[Road]] = defaultdict(list)
        for r in rs:
            by_way[r.osm_id].append(r)
        lane_m, n = 0.0, 0
        for osm_id, ws in by_way.items():
            ws.sort(key=lambda r: r.seg)
            length = sum(r.length_m for r in ws)
            if length < 40:  # slivers where a street just clips the catchment edge
                continue
            db.add(SurveyLane(study_id=st.id, work_unit_id=u.id, road_id=ws[0].id,
                              name=ws[0].name, highway=ws[0].highway,
                              coords=[r.coords for r in ws], length_m=round(length, 1), h3_9=ws[0].h3_9))
            lane_m += length
            n += 1
        u.lane_count, u.lane_m = n, round(lane_m, 1)
        units.append(u)
    st.status = "planned"
    db.flush()
    return units


# ------------------------------------------------------------------ roll-up

def latest_observations(db: Session, lane_ids: list[int]) -> dict[int, LaneObservation]:
    latest: dict[int, LaneObservation] = {}
    for i in range(0, len(lane_ids), 900):
        for ob in db.scalars(select(LaneObservation).where(LaneObservation.lane_id.in_(lane_ids[i:i + 900]))):
            cur = latest.get(ob.lane_id)
            if cur is None or ob.captured_at > cur.captured_at:
                latest[ob.lane_id] = ob
    return latest


def rollup(db: Session, st: CatchmentStudy) -> dict:
    """Insights over the *requested* catchment, using lanes from this study and any reused ones."""
    source_ids = [st.id] + [r["study_id"] for r in (st.reused or [])]
    req = set(st.requested_cells)
    lanes = [l for l in db.scalars(select(SurveyLane).where(SurveyLane.study_id.in_(source_ids))) if l.h3_9 in req]
    obs = latest_observations(db, [l.id for l in lanes])
    total_m = sum(l.length_m for l in lanes) or 1.0
    surveyed = [l for l in lanes if l.id in obs and obs[l.id].data.get("status", "done") == "done"]
    inaccessible = [l for l in lanes if l.id in obs and obs[l.id].data.get("status") == "inaccessible"]
    surveyed_m = sum(l.length_m for l in surveyed) or 0.0

    hh = kir = sup = 0
    sec = Counter()
    housing = Counter()
    brands = Counter()
    foot = []
    for l in surveyed:
        d = obs[l.id].data
        h = int(d.get("households") or 0)
        hh += h
        kir += int(d.get("kiranas") or 0)
        sup += int(d.get("supermarkets") or 0)
        if d.get("sec"):
            sec[d["sec"]] += max(h, 1)
        if d.get("housing_type"):
            housing[d["housing_type"]] += 1
        for b in d.get("competitor_brands") or []:
            brands[b] += 1
        if d.get("footfall"):
            foot.append({"low": 1, "medium": 2, "high": 3}.get(d["footfall"], 2))

    scale = total_m / surveyed_m if surveyed_m else 0
    hh_est = round(hh * scale)
    outlets_est = max(round((kir + sup) * scale), 1)
    sec_total = sum(sec.values()) or 1
    model = F.aggregate(db, list(req))
    model_hh = round(model.sums["est_households"])
    return {
        "area_km2": round(geo.cells_area_km2(req), 2),
        "lanes_total": len(lanes), "lanes_surveyed": len(surveyed), "lanes_inaccessible": len(inaccessible),
        "lane_km_total": round(total_m / 1000, 2), "lane_km_surveyed": round(surveyed_m / 1000, 2),
        "coverage": round(surveyed_m / total_m, 2),
        "households_observed": hh, "households_estimated": hh_est,
        "kiranas_observed": kir, "supermarkets_observed": sup,
        "households_per_outlet": round(hh_est / outlets_est) if surveyed_m else None,
        "sec_mix": {k: round(sec[k] / sec_total, 2) for k in SEC_ORDER if sec[k]},
        "sec_ab_share": round((sec["A"] + sec["B"]) / sec_total, 2) if sec else None,
        "housing_mix": dict(housing.most_common()),
        "competitor_brands": dict(brands.most_common(10)),
        "footfall_index": round(sum(foot) / len(foot), 2) if foot else None,
        "model_households": model_hh,
        "model_households_delta_pct": round((hh_est - model_hh) / model_hh * 100) if model_hh and surveyed_m else None,
        "sources": source_ids, "computed_at": utcnow().isoformat() + "Z",
    }


def progress(db: Session, st: CatchmentStudy) -> dict:
    units = []
    all_done = all_m = 0.0
    for u in st.work_units:
        done = [l for l in u.lanes if l.status != "pending"]
        dm = sum(l.length_m for l in done)
        units.append({"id": u.id, "lanes_done": len(done), "lanes": len(u.lanes),
                      "pct": round(dm / u.lane_m, 2) if u.lane_m else 0})
        all_done += dm
        all_m += u.lane_m
    return {"units": units, "pct": round(all_done / all_m, 2) if all_m else 0}
