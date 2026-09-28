"""Narratives for reports and property evaluations.

Flow: fact sheet (our numbers) -> LLM explains -> grounding check -> accept, or fall back
to a deterministic template. The result always records which path was taken so the UI
can show "AI-written · all 14 figures verified" or "Template narrative (AI unavailable)".
"""
from __future__ import annotations

import json

from .. import llm
from ..llm import grounding

AREA_SYSTEM = """You are a retail expansion analyst for Savomart, a neighbourhood grocery chain in Chennai.
You explain a pre-computed Area Fitness Report to a Business Development manager.

STRICT RULES:
- Use ONLY numbers that appear in the FACTS JSON. Never estimate, extrapolate or invent figures.
- You may round (e.g. 48,213 -> 48k) but not compute new quantities (no sums, ratios or growth rates).
- If something is unknown, say it is unknown. Mark proxies as proxies.
- Be concrete and brief; a manager should be able to decide in 30 seconds.
Return ONLY a JSON object with keys:
  "headline": one sentence verdict,
  "summary": 2-3 sentences,
  "strengths": [3 short bullets],
  "concerns": [2-3 short bullets],
  "scouting_advice": 1-2 sentences on where executives should look first and what to look for."""

PROPERTY_SYSTEM = """You are a retail real-estate analyst for Savomart, a neighbourhood grocery chain in Chennai.
You explain a pre-computed property evaluation to a BD manager who must decide in 30 seconds.

STRICT RULES:
- Use ONLY numbers that appear in the FACTS JSON. Never invent or compute new figures.
- Mention mock/benchmark data as such (rent benchmarks are mock data).
Return ONLY a JSON object with keys:
  "headline": one sentence,
  "summary": 2-3 sentences,
  "next_step": one sentence recommending the next action."""


def _llm_narrative(system: str, facts: dict, required: list[str]) -> dict:
    info = llm.provider_info()
    meta = {"provider": info["provider"], "model": info["model"]}
    if not info["enabled"]:
        return {"ok": False, "meta": {**meta, "mode": "template", "reason": "No LLM configured"}}
    try:
        out = llm.complete_json(system, "FACTS:\n" + json.dumps(facts, ensure_ascii=False, default=str))
    except llm.LLMError as exc:
        return {"ok": False, "meta": {**meta, "mode": "template", "reason": f"AI unavailable: {exc}"[:300]}}
    if any(k not in out for k in required):
        return {"ok": False, "meta": {**meta, "mode": "template", "reason": "AI response missing fields"}}
    g = grounding.check(grounding.texts_of(out), facts)
    if not g["grounded"]:
        return {"ok": False, "meta": {**meta, "mode": "template", "grounding": g,
                                      "reason": f"AI cited figures not in the data ({', '.join(g['untraced'][:5])}); "
                                                "template used instead"}}
    return {"ok": True, "narrative": out, "meta": {**meta, "mode": "ai", "grounding": g}}


# ------------------------------------------------------------------ area

BAND_PHRASE = {"Strong fit": "a strong fit", "Promising": "a promising area", "Marginal": "a marginal fit",
               "Weak fit": "a weak fit"}

def area_facts(name: str, metrics: dict, scored: dict, hotspots: list[dict], confidence: str) -> dict:
    return {
        "area": name,
        "fit_score": scored["score"], "band": scored["band"], "confidence": confidence,
        "pillars": {v["label"]: v["score"] for v in scored["pillars"].values()},
        "area_km2": metrics["area_km2"],
        "estimated_residents": metrics["population"], "estimated_households": metrics["households"],
        "residents_per_km2": metrics["pop_density"],
        "grocery_outlets_mapped": metrics["grocery_outlets"], "supermarkets_mapped": metrics["supermarkets"],
        "residents_per_grocery_outlet": metrics["people_per_outlet"],
        "footfall_generators": metrics["generators"],
        "apartment_share_pct": round(metrics["apartment_share"] * 100, 1),
        "nearest_savomart": metrics["nearest_stores"][:1],
        "hotspots": [{"rank": h["rank"], "near": h.get("label"), "score": h["score"], "reasons": h["reasons"]}
                     for h in hotspots[:3]],
        "notes": ["Resident counts are 2011-census-calibrated estimates", "OSM under-counts small kirana stores"],
    }


def area_template(facts: dict, scored: dict) -> dict:
    pillars = sorted(scored["pillars"].values(), key=lambda p: p["score"], reverse=True)
    top, low = pillars[:3], pillars[-2:]
    hs = facts["hotspots"]
    near = facts["nearest_savomart"][0] if facts["nearest_savomart"] else None
    return {
        "headline": f"{facts['area']} is {BAND_PHRASE.get(facts['band'], facts['band'])} for Savomart "
                    f"(score {facts['fit_score']}/100, {facts['confidence'].lower()} confidence).",
        "summary": f"An estimated {facts['estimated_residents']:,} residents live across {facts['area_km2']} km², "
                   f"with {facts['grocery_outlets_mapped']} grocery outlets mapped in OSM "
                   f"(~{facts['residents_per_grocery_outlet']:,} residents per outlet)."
                   + (f" The nearest Savomart is {near['name']} at {near['distance_km']} km." if near else ""),
        "strengths": [f"{p['label']} scores {p['score']:.0f}/100 — {p['description'][0].lower() + p['description'][1:]}"
                      for p in top],
        "concerns": [f"{p['label']} scores only {p['score']:.0f}/100 — {p['description'][0].lower() + p['description'][1:]}"
                     for p in low if p["score"] < 60] or ["No pillar scores below 60/100."],
        "scouting_advice": (f"Start with hotspot #1 near {hs[0]['near']} — " + "; ".join(hs[0]["reasons"][:2]) + "."
                            if hs else "No clear hotspot stands out; scout along the arterial roads first."),
    }


def area_narrative(facts: dict, scored: dict) -> tuple[dict, dict]:
    res = _llm_narrative(AREA_SYSTEM, facts, ["headline", "summary", "strengths", "concerns", "scouting_advice"])
    if res["ok"]:
        return res["narrative"], res["meta"]
    return area_template(facts, scored), res["meta"]


# ------------------------------------------------------------------ property

def property_template(facts: dict) -> dict:
    rec = {"go": "Recommend progressing", "consider": "Worth a closer look", "no_go": "Not recommended"}[facts["recommendation"]]
    top_ins = facts["insights"][:2]
    top_risk = facts["risks"][:1]
    return {
        "headline": f"{rec}: {facts['property']} scores {facts['score']}/100.",
        "summary": " ".join(top_ins + top_risk),
        "next_step": {"go": "Schedule a site visit and request a catchment study to confirm demand on the ground.",
                      "consider": "Ask the executive to verify the flagged items before shortlisting.",
                      "no_go": "Reject unless the flagged risks can be negotiated away."}[facts["recommendation"]],
    }


def property_narrative(facts: dict) -> tuple[dict, dict]:
    res = _llm_narrative(PROPERTY_SYSTEM, facts, ["headline", "summary", "next_step"])
    if res["ok"]:
        return res["narrative"], res["meta"]
    return property_template(facts), res["meta"]
