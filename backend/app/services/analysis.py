"""M1 — Area Fitness Report pipeline (runs as a background job)."""
from __future__ import annotations

import h3
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import geo
from ..models import AreaReport, BaselineMeta, DataSnapshot, Job, Road, utcnow
from . import features as F
from . import narrative as N
from . import scoring as S
from .jobs import handler

HOTSPOT_RING = 2           # res-9 ring => ~600 m walking catchment around a candidate cell
HOTSPOT_MIN_SEP_M = 800    # hotspots at least this far apart
HOTSPOT_COUNT = 5


def data_versions(db: Session) -> dict:
    """Latest snapshot per source — stamped onto every report/evaluation."""
    out = {}
    sub = select(DataSnapshot.source, func.max(DataSnapshot.id).label("mid")).group_by(DataSnapshot.source).subquery()
    for snap in db.scalars(select(DataSnapshot).join(sub, DataSnapshot.id == sub.c.mid)):
        out[snap.source] = {"fetched_at": snap.fetched_at.isoformat() + "Z", "source_timestamp": snap.source_timestamp,
                            "records": snap.record_count, "notes": snap.notes}
    info = db.get(BaselineMeta, "info")
    out["model"] = {"version": S.MODEL_VERSION, **(info.value if info else {})}
    return out


def _visibility(cs) -> float:
    if not cs:
        return 0.0
    return min(100.0, (cs.major_road_m or 0) / 300 * 100 * 0.7 + (cs.road_m or 0) / 2500 * 100 * 0.3)


def find_hotspots(db: Session, cells8: list[str], dist: S.Distributions, stores, count: int = HOTSPOT_COUNT) -> list[dict]:
    cells9 = geo.children(cells8, 9)
    ring_cells = set()
    for c in cells9:
        ring_cells.update(h3.grid_disk(c, HOTSPOT_RING))
    cache = F.load_cellstats(db, ring_cells)
    cands = []
    for c in cells9:
        cs = cache.get(c)
        if not cs or (cs.est_population or 0) < 200:
            continue
        lat, lng = h3.cell_to_latlng(c)
        m = F.derive(F.aggregate(db, h3.grid_disk(c, HOTSPOT_RING), cache), lat, lng, stores)
        demand = dist.pct("pop_density", m["pop_density"])
        gap = 0.6 * dist.pct("people_per_outlet", m["people_per_outlet"]) + \
            0.4 * (100 - dist.pct("supermarkets_per_10k", m["supermarkets_per_10k"]))
        activity = dist.pct("generators_per_km2", m["generators_per_km2"])
        vis = _visibility(cs)
        net = S.network_score(m["nearest_store_km"])
        score = round(0.35 * demand + 0.25 * gap + 0.15 * activity + 0.15 * vis + 0.10 * net, 1)
        cands.append((score, c, lat, lng, m, {"demand": demand, "gap": round(gap, 1), "activity": activity,
                                              "visibility": round(vis, 1), "network": net}))
    cands.sort(key=lambda x: -x[0])
    picked: list[dict] = []
    for score, c, lat, lng, m, parts in cands:
        if any(geo.haversine_m(lat, lng, p["lat"], p["lng"]) < HOTSPOT_MIN_SEP_M for p in picked):
            continue
        road = db.scalar(select(Road).where(Road.h3_9 == c, Road.name.is_not(None))
                         .order_by(Road.highway.in_(["trunk", "primary", "secondary"]).desc(), Road.length_m.desc()))
        near = m["nearest_stores"][0] if m["nearest_stores"] else None
        reasons = [f"~{m['population']:,} residents within ~600 m (est.)"]
        reasons.append(f"{m['grocery_outlets']} grocery outlets mapped within ~600 m"
                       if m["grocery_outlets"] else "No grocery outlets mapped within ~600 m")
        if road:
            reasons.append(f"On/near {road.name} ({road.highway})")
        if m["generators"]:
            reasons.append(f"{m['generators']} footfall generators nearby (schools, clinics, transit…)")
        if near:
            reasons.append(f"{near['distance_km']} km from Savomart {near['name']}")
        picked.append({
            "rank": len(picked) + 1, "h3": c, "lat": round(lat, 6), "lng": round(lng, 6), "score": score,
            "label": (road.name if road else None) or "Unnamed street cluster",
            "parts": parts, "reasons": reasons,
            "metrics": {k: m[k] for k in ("population", "grocery_outlets", "supermarkets", "generators",
                                          "nearest_store_km")},
        })
        if len(picked) >= count:
            break
    return picked


def build_profile(db: Session, metrics: dict, cells8: list[str]) -> dict:
    """What the area is like — people, homes, businesses, amenities, competition, Savomart."""
    p = metrics["pois"]
    cells9 = set(geo.children(cells8, 9))
    comp = []
    from ..models import Poi
    for i in range(0, len(cells9), 900):
        chunk = list(cells9)[i:i + 900]
        for poi in db.scalars(select(Poi).where(Poi.h3_9.in_(chunk), Poi.category.in_(["supermarket", "grocery", "fresh_food", "mall"]))):
            comp.append({"name": poi.name or poi.tag, "brand": poi.brand, "category": poi.category,
                         "lat": poi.lat, "lng": poi.lng})
    brands: dict[str, int] = {}
    for c in comp:
        if c["category"] == "supermarket":
            key = c["brand"] or c["name"] or "Unnamed supermarket"
            brands[key] = brands.get(key, 0) + 1
    return {
        "people": {"population": metrics["population"], "households": metrics["households"],
                   "density": metrics["pop_density"], "estimate_note": "Census-2011-calibrated dasymetric estimate"},
        "homes": {"buildings_mapped": metrics["buildings"], "apartment_share": metrics["apartment_share"]},
        "businesses": {"retail": p["retail"], "offices": p["office"], "food": p["food"], "banks": p["bank"],
                       "fuel": p["fuel"], "malls": p["mall"]},
        "amenities": {"schools": p["school"], "colleges": p["college"], "healthcare": p["healthcare"],
                      "pharmacies": p["pharmacy"], "transit": p["transit"], "worship": p["worship"],
                      "markets": p["market"]},
        "competition": {"supermarkets": p["supermarket"], "grocery": p["grocery"], "fresh_food": p["fresh_food"],
                        "people_per_outlet": metrics["people_per_outlet"],
                        "top_brands": sorted(brands.items(), key=lambda x: -x[1])[:8],
                        "points": comp[:400]},
        "savomart": {"nearest": metrics["nearest_stores"]},
        "roads": {"road_km": metrics["road_km"], "road_density": metrics["road_density"]},
    }


def _fail_report(db: Session, job: Job, exc: Exception) -> None:
    rep = db.get(AreaReport, job.ref_id)
    if rep:
        rep.status, rep.error = "failed", str(exc)[:500]
        db.commit()


@handler("area_analysis", steps=[
    ("area", "Resolve area & grid cells"),
    ("data", "Load public data (OSM, population)"),
    ("network", "Check Savomart store network"),
    ("score", "Score fit against Chennai baseline"),
    ("hotspots", "Find scouting hotspots"),
    ("narrative", "Write explanation (AI, fact-checked)"),
], on_fail=_fail_report)
def run_area_analysis(ctx) -> None:
    db = ctx.db
    rep = db.get(AreaReport, ctx.ref_id)
    rep.status = "running"
    db.commit()

    ctx.step("area", "running")
    cells8 = rep.cells
    cells9 = geo.children(cells8, 9)
    rep.area_km2 = round(geo.cells_area_km2(cells8), 2)
    ctx.step("area", "done", f"{len(cells8)} cells · {rep.area_km2} km²")

    ctx.step("data", "running")
    agg = F.aggregate(db, cells9)
    if agg.n_cells_with_data == 0:
        raise RuntimeError("No public data found for this area — is it inside the ingested Chennai region?")
    ctx.step("data", "done", f"{agg.n_cells_with_data}/{agg.n_cells} fine cells have mapped data")

    ctx.step("network", "running")
    stores = F.chennai_stores(db)
    metrics = F.derive(agg, rep.center_lat, rep.center_lng, stores)
    near = metrics["nearest_stores"][0] if metrics["nearest_stores"] else None
    ctx.step("network", "done", f"Nearest: {near['name']} ({near['distance_km']} km)" if near else "No stores")

    ctx.step("score", "running")
    dist = S.Distributions.load(db)
    scored = S.score(metrics, dist)
    conf, conf_reasons = S.confidence(metrics)
    ctx.step("score", "done", f"{scored['score']}/100 · {scored['band']}")

    ctx.step("hotspots", "running")
    hotspots = find_hotspots(db, cells8, dist, stores)
    ctx.step("hotspots", "done" if hotspots else "warning",
             f"{len(hotspots)} hotspots" if hotspots else "No populated cells to rank")

    rep.score, rep.band, rep.confidence = scored["score"], scored["band"], conf
    rep.pillars = scored["pillars"]
    rep.indicators = scored["indicators"]
    rep.profile = {**build_profile(db, metrics, cells8), "confidence_reasons": conf_reasons}
    rep.hotspots = hotspots
    rep.data_versions = data_versions(db)
    db.commit()

    ctx.step("narrative", "running")
    facts = N.area_facts(rep.name, metrics, scored, hotspots, conf)
    text, meta = N.area_narrative(facts, scored)
    rep.narrative = {**text, "meta": meta}
    ctx.step("narrative", "done" if meta.get("mode") == "ai" else "warning",
             "AI narrative, all figures verified" if meta.get("mode") == "ai" else meta.get("reason"))

    rep.status, rep.completed_at, rep.error = "completed", utcnow(), None
    db.commit()
