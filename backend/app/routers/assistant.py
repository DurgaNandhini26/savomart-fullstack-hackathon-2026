"""Bonus — conversational analyst for BD managers, grounded in our own data.

Retrieval first, generation second: we detect the entities the question is about
(localities, pincodes, property codes, study codes), compute/fetch their facts with the
same scoring code the reports use, and only then let the LLM phrase an answer from those
facts. The answer passes the same number-grounding check; without an LLM the user gets
a structured comparison generated from the facts directly.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import geo, llm
from ..auth import require
from ..db import get_db
from ..llm import grounding
from ..models import AreaReport, CatchmentStudy, OpportunityCell, Place, Property, PropertyEvaluation, User
from ..services import areas as A
from ..services import features as F
from ..services import scoring as S

router = APIRouter(prefix="/api")

SYSTEM = """You are SiteScout, an analyst assistant for Savomart's BD team in Chennai.
Answer the manager's question using ONLY the FACTS JSON. Do not invent numbers, places or data.
If the facts do not answer the question, say what is missing and suggest which report or study would answer it.
Estimates (residents) are census-calibrated estimates; OSM under-counts small kiranas — say so when relevant.
Return ONLY JSON: {"answer": "<markdown, <= 180 words>", "follow_ups": ["<short question>", "<short question>"]}"""


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def _localities(db: Session, q: str) -> list[Place]:
    ql = q.lower()
    hits: list[Place] = []
    names = db.execute(select(Place.id, Place.name).where(Place.kind == "locality",
                                                         Place.place_type.in_(A.LOCALITY_TYPES))).all()
    for pid, name in sorted(names, key=lambda x: -len(x[1])):
        n = name.lower()
        if len(n) >= 4 and re.search(rf"\b{re.escape(n)}\b", ql) and not any(n in h.name.lower() for h in hits):
            hits.append(db.get(Place, pid))
        if len(hits) >= 4:
            break
    return hits


def _area_facts(db: Session, sel_type: str, value: str, label: str, stores, dist) -> dict:
    res = A.resolve(db, sel_type, value, None)
    cells9 = geo.children(res["cells"], 9)
    lat, lng = geo.centroid_of_cells(res["cells"])
    m = F.derive(F.aggregate(db, cells9), lat, lng, stores)
    sc = S.score(m, dist)
    rep = db.scalar(select(AreaReport).where(AreaReport.status == "completed", func.lower(AreaReport.name).like(f"%{label.lower()}%"))
                    .order_by(AreaReport.id.desc()))
    return {"area": label, "fit_score": sc["score"], "band": sc["band"],
            "pillars": {v["label"]: v["score"] for v in sc["pillars"].values()},
            "area_km2": m["area_km2"], "estimated_residents": m["population"], "residents_per_km2": m["pop_density"],
            "grocery_outlets_mapped": m["grocery_outlets"], "supermarkets_mapped": m["supermarkets"],
            "residents_per_outlet": m["people_per_outlet"], "footfall_generators": m["generators"],
            "nearest_savomart": m["nearest_stores"][0] if m["nearest_stores"] else None,
            "saved_report_id": rep.id if rep else None}


@router.post("/assistant/ask")
def ask(body: AskIn, db: Session = Depends(get_db), _: User = Depends(require("bd_manager"))):
    q = body.question
    stores = F.chennai_stores(db)
    dist = S.Distributions.load(db)
    facts: dict = {"question": q, "areas": [], "properties": [], "studies": []}
    sources: list[dict] = []

    for place in _localities(db, q):
        try:
            facts["areas"].append(_area_facts(db, "locality", str(place.id), place.name, stores, dist))
            sources.append({"type": "locality", "label": place.name})
        except A.AreaError:
            pass
    for pin in re.findall(r"\b(6\d{5})\b", q)[:4]:
        try:
            facts["areas"].append(_area_facts(db, "pincode", pin, f"PIN {pin}", stores, dist))
            sources.append({"type": "pincode", "label": pin})
        except A.AreaError:
            pass
    for code in re.findall(r"\bPR-\d{4}\b", q.upper())[:4]:
        p = db.scalar(select(Property).where(Property.code == code))
        if p:
            ev = db.scalar(select(PropertyEvaluation).where(PropertyEvaluation.property_id == p.id,
                                                            PropertyEvaluation.status == "completed")
                           .order_by(PropertyEvaluation.version.desc()))
            facts["properties"].append({"code": p.code, "title": p.title, "stage": p.stage, "locality": p.locality,
                                        "score": p.latest_score, "recommendation": p.latest_recommendation,
                                        "rent_monthly": p.rent_monthly, "carpet_area_sqft": p.carpet_area_sqft,
                                        "insights": ev.insights if ev else None, "risks": ev.risks if ev else None})
            sources.append({"type": "property", "label": p.code, "id": p.id})
    for code in re.findall(r"\bCS-\d{3}\b", q.upper())[:3]:
        st = db.scalar(select(CatchmentStudy).where(CatchmentStudy.code == code))
        if st:
            facts["studies"].append({"code": st.code, "title": st.title, "status": st.status, "insights": st.insights})
            sources.append({"type": "study", "label": st.code, "id": st.id})

    wants_pipeline = any(w in q.lower() for w in ("pipeline", "properties", "shortlist", "approved", "pending"))
    if wants_pipeline or not (facts["areas"] or facts["properties"] or facts["studies"]):
        facts["pipeline"] = dict(db.execute(select(Property.stage, func.count()).group_by(Property.stage)).all())
        top = []
        seen = set()
        for o in db.scalars(select(OpportunityCell).order_by(OpportunityCell.score.desc()).limit(80)):
            if o.locality in seen:
                continue
            seen.add(o.locality)
            top.append({"locality": o.locality, "opportunity_score": o.score,
                        "estimated_residents_1_5km": o.features.get("population"),
                        "nearest_store_km": o.features.get("nearest_store_km")})
            if len(top) >= 6:
                break
        facts["top_opportunities"] = top
        sources.append({"type": "opportunity_map", "label": "City-wide opportunity map"})

    info = llm.provider_info()
    meta = {"provider": info["provider"], "model": info["model"], "mode": "template"}
    answer, follow = None, []
    if info["enabled"]:
        try:
            out = llm.complete_json(SYSTEM, "FACTS:\n" + __import__("json").dumps(facts, default=str), max_tokens=700)
            g = grounding.check([out.get("answer", "")], facts)
            if g["grounded"] and out.get("answer"):
                answer, follow = out["answer"], out.get("follow_ups", [])[:3]
                meta.update(mode="ai", grounding=g)
            else:
                meta["reason"] = f"AI cited figures not in the data ({', '.join(g['untraced'][:4])})"
        except llm.LLMError as exc:
            meta["reason"] = str(exc)[:200]
    else:
        meta["reason"] = "No LLM configured — showing the facts directly"
    if answer is None:
        answer = _template(facts)
        follow = ["Which of these has the biggest competition gap?", "Where are our un-scouted opportunities?"]
    return {"answer": answer, "follow_ups": follow, "facts": facts, "sources": sources, "meta": meta}


def _template(f: dict) -> str:
    lines = []
    if f["areas"]:
        ranked = sorted(f["areas"], key=lambda a: -a["fit_score"])
        lines.append("**Area comparison** (live from the scoring model):\n")
        lines.append("| Area | Fit | Residents (est.) | Residents / outlet | Nearest Savomart |")
        lines.append("|---|---|---|---|---|")
        for a in ranked:
            ns = a["nearest_savomart"]
            lines.append(f"| {a['area']} | **{a['fit_score']}** {a['band']} | {a['estimated_residents']:,} | "
                         f"{a['residents_per_outlet']:,} | {ns['name'] + ' · ' + str(ns['distance_km']) + ' km' if ns else '—'} |")
        best = ranked[0]
        top_p = max(best["pillars"].items(), key=lambda x: x[1])
        lines.append(f"\n**{best['area']}** leads; its strongest pillar is *{top_p[0]}* ({top_p[1]:.0f}/100).")
    for p in f["properties"]:
        lines.append(f"\n**{p['code']} {p['title']}** — stage *{p['stage']}*, score {p['score']} ({p['recommendation']}).")
    for s in f["studies"]:
        lines.append(f"\n**{s['code']}** — {s['status']}.")
    if f.get("top_opportunities") and not f["areas"]:
        lines.append("**Highest-scoring neighbourhoods on the opportunity map:**\n")
        for t in f["top_opportunities"]:
            lines.append(f"- {t['locality']}: {t['opportunity_score']} (≈{t['estimated_residents_1_5km']:,} residents within ~1.5 km, "
                         f"{t['nearest_store_km']} km to nearest Savomart)")
    if f.get("pipeline"):
        lines.append("\nPipeline: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in f["pipeline"].items()))
    if not lines:
        lines.append("I couldn't match that to an area, pincode, property (PR-0001) or study (CS-001). "
                     "Try naming a locality, e.g. *compare Velachery and Tambaram*.")
    return "\n".join(lines)
