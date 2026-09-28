"""M2 — automatic property evaluation.

Four pillars, each 0-100:
  catchment   (40%) public data within ~800 m (same features/percentiles as area reports),
                    replaced/adjusted by ground-truth catchment-study data when available
  site        (25%) what the executive captured: size, frontage, floor, road, parking, power...
  commercials (20%) rent vs locality benchmark (MOCK — no open rent data), deposit, lease
  network     (15%) distance to the nearest Savomart store

Evaluations are versioned: a new version is created when details change or a catchment
study completes, so a manager can see *why* the recommendation moved.
"""
from __future__ import annotations

import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import geo
from ..models import CatchmentStudy, Job, Property, PropertyEvaluation, utcnow
from . import features as F
from . import narrative as N
from . import scoring as S
from .analysis import data_versions
from .jobs import handler

CATCHMENT_M = 800
WEIGHTS = {"catchment": 0.40, "site": 0.25, "commercials": 0.20, "network": 0.15}
IDEAL_SQFT = (2000, 4000)
CITY_CENTRE = (13.0418, 80.2341)  # T. Nagar — Chennai's retail centre of gravity


def rent_benchmark(lat: float, lng: float, on_major_road: bool) -> float:
    """MOCK ₹/sqft/month benchmark for ground-floor retail.

    There is no open rent dataset for Chennai. This smooth decay from the retail core
    (≈ ₹120 in T. Nagar down to ≈ ₹35 at the periphery, +15% on arterial roads) is a
    placeholder so the workflow is demoable; it is labelled MOCK everywhere it appears.
    Replace with broker/99acres/internal lease data.
    """
    d_km = geo.haversine_m(lat, lng, *CITY_CENTRE) / 1000
    base = 35 + 85 * math.exp(-d_km / 9)
    return round(base * (1.15 if on_major_road else 1.0), 1)


def _clip(x: float) -> float:
    return max(0.0, min(100.0, x))


def site_score(p: Property) -> tuple[float, list[str], list[str], list[dict]]:
    ins, risks, parts = [], [], []

    def part(label, score, note):
        parts.append({"label": label, "score": round(score), "note": note})

    if p.carpet_area_sqft:
        a = p.carpet_area_sqft
        if IDEAL_SQFT[0] <= a <= IDEAL_SQFT[1]:
            s = 100
            ins.append(f"{int(a):,} sq ft is in Savomart's ideal format range ({IDEAL_SQFT[0]:,}–{IDEAL_SQFT[1]:,}).")
        elif a < IDEAL_SQFT[0]:
            s = _clip(100 - (IDEAL_SQFT[0] - a) / 12)
            (risks if a < 1200 else ins).append(f"{int(a):,} sq ft is below the ideal {IDEAL_SQFT[0]:,} sq ft.")
        else:
            s = _clip(100 - (a - IDEAL_SQFT[1]) / 40)
            if a > 6000:
                risks.append(f"{int(a):,} sq ft is larger than needed — higher rent for unused space.")
        part("Size", s, f"{int(a):,} sq ft")
    else:
        part("Size", 40, "Not captured")
        risks.append("Carpet area missing — ask the executive to measure.")

    if p.frontage_ft:
        s = _clip((p.frontage_ft - 10) / 20 * 100)
        part("Frontage", s, f"{p.frontage_ft:g} ft")
        if p.frontage_ft < 15:
            risks.append(f"Narrow frontage ({p.frontage_ft:g} ft) limits visibility and signage.")
        elif p.frontage_ft >= 25:
            ins.append(f"Wide {p.frontage_ft:g} ft frontage gives strong street visibility.")
    else:
        part("Frontage", 50, "Not captured")

    floor_s = {"ground": 100, "ground+first": 85, "first": 35, "basement": 20}.get(p.floor or "", 50)
    part("Floor", floor_s, p.floor or "Not captured")
    if p.floor in ("first", "basement"):
        risks.append(f"Store on {p.floor} floor — grocery footfall drops sharply off the ground floor.")

    road_s = {"main_road": 100, "secondary": 70, "interior": 35}.get(p.road_facing or "", 50)
    part("Road", road_s, (p.road_facing or "unknown").replace("_", " "))
    if p.road_facing == "main_road":
        ins.append("Faces a main road.")
    elif p.road_facing == "interior":
        risks.append("Interior street — relies on walk-in residents only.")

    park = min(100, (p.parking_2w or 0) * 6 + (p.parking_4w or 0) * 20)
    part("Parking", park, f"{p.parking_2w or 0} two-wheeler · {p.parking_4w or 0} car")
    if park < 30:
        risks.append("Little or no parking for customers.")

    if p.visibility:
        part("Visibility", p.visibility * 20, f"{p.visibility}/5 (executive's rating)")
    if p.power_kw is not None:
        part("Power", _clip(p.power_kw / 20 * 100), f"{p.power_kw:g} kW")
        if p.power_kw < 10:
            risks.append(f"Only {p.power_kw:g} kW power — chillers/freezers typically need 15–20 kW.")
    if p.truck_access is not None:
        part("Truck access", 100 if p.truck_access else 30, "Yes" if p.truck_access else "No")
        if not p.truck_access:
            risks.append("No truck access for replenishment.")

    weights = {"Size": 0.3, "Frontage": 0.15, "Floor": 0.2, "Road": 0.15, "Parking": 0.1, "Visibility": 0.05,
               "Power": 0.03, "Truck access": 0.02}
    tw = sum(weights[x["label"]] for x in parts)
    score = sum(x["score"] * weights[x["label"]] for x in parts) / tw
    return round(score, 1), ins, risks, parts


def commercials_score(p: Property, benchmark: float) -> tuple[float, list[str], list[str], dict]:
    ins, risks = [], []
    facts: dict = {"rent_benchmark_psf_mock": benchmark}
    if p.rent_monthly and p.carpet_area_sqft:
        psf = p.rent_monthly / p.carpet_area_sqft
        ratio = psf / benchmark
        facts.update(rent_psf=round(psf, 1), rent_vs_benchmark_pct=round((ratio - 1) * 100))
        s = _clip(100 - max(0, ratio - 0.8) * 125)  # ≤0.8× benchmark → 100, 1.0× → 75, 1.4× → 25
        if ratio <= 0.95:
            ins.append(f"Rent ₹{psf:.0f}/sq ft is {abs(round((ratio - 1) * 100))}% below the locality benchmark (mock).")
        elif ratio > 1.2:
            risks.append(f"Rent ₹{psf:.0f}/sq ft is {round((ratio - 1) * 100)}% above the locality benchmark (mock).")
    elif p.rent_negotiable or not p.rent_monthly:
        s = 50
        risks.append("Rent not captured yet — commercials are unscored.")
    else:
        s = 50
    if p.deposit_months is not None:
        facts["deposit_months"] = p.deposit_months
        if p.deposit_months > 10:
            s -= 15
            risks.append(f"High deposit ({p.deposit_months:g} months).")
        elif p.deposit_months <= 6:
            s += 5
    if p.lease_years is not None:
        facts["lease_years"] = p.lease_years
        if p.lease_years < 5:
            s -= 15
            risks.append(f"Short lease ({p.lease_years:g} years) — fit-out cost may not be recovered.")
        elif p.lease_years >= 9:
            s += 5
            ins.append(f"Long {p.lease_years:g}-year lease protects the fit-out investment.")
    return round(_clip(s), 1), ins, risks, facts


def ground_truth_for(db: Session, prop: Property) -> CatchmentStudy | None:
    """Latest completed catchment study covering this property (own or reused)."""
    c9 = prop.h3_9
    for st in db.scalars(select(CatchmentStudy).where(CatchmentStudy.status.in_(["completed", "reused"]))
                         .order_by(CatchmentStudy.completed_at.desc().nulls_last())):
        if st.insights and c9 in set(st.requested_cells):
            return st
    return None


def evaluate(db: Session, prop: Property) -> dict:
    stores = F.chennai_stores(db)
    dist = S.Distributions.load(db)
    cells = geo.disk_cells(prop.lat, prop.lng, CATCHMENT_M, 9)
    m = F.derive(F.aggregate(db, cells), prop.lat, prop.lng, stores)
    area_scored = S.score(m, dist)
    pl = area_scored["pillars"]
    catch = (pl["demand"]["score"] * 0.4 + pl["gap"]["score"] * 0.3 + pl["activity"]["score"] * 0.2
             + pl["spending"]["score"] * 0.1)
    insights, risks = [], []
    gt = ground_truth_for(db, prop)
    gt_facts = None
    if gt and gt.insights:
        gi = gt.insights
        gt_facts = {k: gi.get(k) for k in ("households_estimated", "households_per_outlet", "sec_ab_share",
                                           "footfall_index", "kiranas_observed", "supermarkets_observed",
                                           "coverage", "model_households_delta_pct")}
        # ground truth replaces the modelled demand/gap where we have it
        hh_po = gi.get("households_per_outlet") or 0
        gt_gap = _clip(hh_po / 250 * 100)  # ~250 households per outlet ≈ well served
        gt_demand = _clip((gi.get("households_estimated") or 0) / 6000 * 100)
        affl = _clip((gi.get("sec_ab_share") or 0) * 150)
        catch = 0.4 * gt_demand + 0.3 * gt_gap + 0.2 * _clip((gi.get("footfall_index") or 1) / 3 * 100) + 0.1 * affl
        insights.append(f"Ground-truthed by catchment study {gt.code}: ~{gi.get('households_estimated', 0):,} households, "
                        f"{gi.get('kiranas_observed', 0)} kiranas and {gi.get('supermarkets_observed', 0)} supermarkets observed.")
        if (gi.get("model_households_delta_pct") or 0) < -25:
            risks.append(f"Survey found {abs(gi['model_households_delta_pct'])}% fewer households than our model estimated.")

    catch = round(catch, 1)
    road = F.nearest_road(db, prop.lat, prop.lng)
    on_major = bool(road and road["highway"] in ("trunk", "primary", "secondary"))
    bench = rent_benchmark(prop.lat, prop.lng, on_major)
    site, s_ins, s_risk, site_parts = site_score(prop)
    comm, c_ins, c_risk, comm_facts = commercials_score(prop, bench)
    net = S.network_score(m["nearest_store_km"])

    insights += [f"~{m['population']:,} residents within {CATCHMENT_M} m (est.), "
                 f"{m['grocery_outlets']} grocery outlets mapped nearby."]
    near = m["nearest_stores"][0] if m["nearest_stores"] else None
    if near and near["distance_km"] < 1.5:
        risks.append(f"Only {near['distance_km']} km from Savomart {near['name']} — likely cannibalisation.")
    elif near and 2 <= near["distance_km"] <= 6:
        insights.append(f"{near['distance_km']} km from Savomart {near['name']}: new catchment inside the supply cluster.")
    if m["supermarkets"] >= 4:
        risks.append(f"{m['supermarkets']} supermarkets already within {CATCHMENT_M} m.")
    insights += s_ins + c_ins
    risks += s_risk + c_risk
    for w in prop.data_quality or []:
        risks.append(f"Data check: {w}")

    pillars = {
        "catchment": {"label": "Catchment" + (" (ground-truthed)" if gt_facts else ""), "score": catch,
                      "weight": WEIGHTS["catchment"]},
        "site": {"label": "Site quality", "score": site, "weight": WEIGHTS["site"], "parts": site_parts},
        "commercials": {"label": "Commercials", "score": comm, "weight": WEIGHTS["commercials"]},
        "network": {"label": "Network fit", "score": net, "weight": WEIGHTS["network"]},
    }
    total = round(sum(p["score"] * p["weight"] for p in pillars.values()), 1)
    critical = [r for r in risks if any(k in r for k in ("cannibalisation", "floor —", "above the locality"))]
    if prop.carpet_area_sqft and prop.carpet_area_sqft < 800:
        critical.append("too small")
    rec = "go" if total >= 68 and not critical else "consider" if total >= 50 else "no_go"
    if rec == "go" and len(critical) >= 1:
        rec = "consider"

    facts = {
        "property": prop.title, "score": total, "recommendation": rec,
        "pillars": {k: v["score"] for k, v in pillars.items()},
        "catchment_radius_m": CATCHMENT_M, "residents_est": m["population"], "households_est": m["households"],
        "grocery_outlets_mapped": m["grocery_outlets"], "supermarkets_mapped": m["supermarkets"],
        "footfall_generators": m["generators"], "nearest_savomart": near,
        "nearest_road": road, "carpet_area_sqft": prop.carpet_area_sqft, "frontage_ft": prop.frontage_ft,
        "rent_monthly": prop.rent_monthly, **comm_facts, "ground_truth": gt_facts,
        "insights": insights, "risks": risks,
    }
    return {"score": total, "recommendation": rec, "pillars": pillars, "facts": facts, "insights": insights,
            "risks": risks, "catchment_study_id": gt.id if gt else None,
            "competitors": F.pois_near(db, prop.lat, prop.lng, CATCHMENT_M, ["supermarket", "grocery", "fresh_food"], 60)}


def new_evaluation(db: Session, prop: Property, trigger: str) -> PropertyEvaluation:
    from .jobs import enqueue
    ver = (db.scalar(select(func.max(PropertyEvaluation.version)).where(PropertyEvaluation.property_id == prop.id)) or 0) + 1
    ev = PropertyEvaluation(property_id=prop.id, version=ver, trigger=trigger, status="queued")
    db.add(ev)
    db.commit()
    job = enqueue(db, "property_evaluation", ev.id)
    ev.job_id = job.id
    db.commit()
    return ev


def _fail_eval(db: Session, job: Job, exc: Exception) -> None:
    ev = db.get(PropertyEvaluation, job.ref_id)
    if ev:
        ev.status, ev.error = "failed", str(exc)[:500]
        db.commit()


@handler("property_evaluation", steps=[
    ("public", "Analyse public data within 800 m"),
    ("site", "Score captured site & commercial details"),
    ("recommend", "Recommendation"),
    ("narrative", "Write summary (AI, fact-checked)"),
], on_fail=_fail_eval)
def run_property_evaluation(ctx) -> None:
    db = ctx.db
    ev = db.get(PropertyEvaluation, ctx.ref_id)
    prop = db.get(Property, ev.property_id)
    ev.status = "running"
    db.commit()
    ctx.step("public", "running")
    res = evaluate(db, prop)
    ctx.step("public", "done", f"{res['facts']['residents_est']:,} residents est.")
    ctx.step("site", "done", f"site {res['pillars']['site']['score']} · commercials {res['pillars']['commercials']['score']}")
    ctx.step("recommend", "done", f"{res['score']}/100 → {res['recommendation']}")
    ctx.step("narrative", "running")
    text, meta = N.property_narrative(res["facts"])
    ctx.step("narrative", "done" if meta.get("mode") == "ai" else "warning",
             "AI summary, figures verified" if meta.get("mode") == "ai" else meta.get("reason"))

    prev = db.scalar(select(PropertyEvaluation).where(PropertyEvaluation.property_id == prop.id,
                                                      PropertyEvaluation.status == "completed")
                     .order_by(PropertyEvaluation.version.desc()))
    ev.score, ev.recommendation, ev.pillars = res["score"], res["recommendation"], res["pillars"]
    ev.facts = {**res["facts"], "competitors": res["competitors"],
                "previous": {"version": prev.version, "score": prev.score, "recommendation": prev.recommendation}
                if prev else None}
    ev.insights, ev.risks = res["insights"], res["risks"]
    ev.narrative = {**text, "meta": meta}
    ev.catchment_study_id = res["catchment_study_id"]
    ev.data_versions = data_versions(db)
    ev.status = "completed"
    prop.latest_score, prop.latest_recommendation = res["score"], res["recommendation"]
    prop.updated_at = utcnow()
    db.commit()
