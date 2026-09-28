"""Transparent, rule-based fit scoring.

Why rules and not ML: we have no labelled outcomes (store P&L) yet, and a BD
manager has to be able to see *why* a score is what it is. Every pillar is a
percentile against the whole of Chennai, so "72" always means "better than 72%
of populated neighbourhoods in the city on this dimension".

When store performance data is available, the weights below are the obvious
thing to fit (a regression of store sales on these same pillars).
"""
from __future__ import annotations

import bisect

from sqlalchemy.orm import Session

from ..models import BaselineMeta

MODEL_VERSION = "fit-v1.0"

# pillar -> (weight, label, what it means)
PILLARS: dict[str, tuple[float, str, str]] = {
    "demand": (0.25, "Resident demand", "How many people live here (estimated residents per km²)."),
    "gap": (0.25, "Competition gap", "People per grocery outlet and modern-trade saturation (higher = underserved)."),
    "activity": (0.15, "Daily footfall", "Density of schools, clinics, transit, worship, offices and markets."),
    "spending": (0.10, "Spending power (proxy)", "Banks, restaurants/cafés, malls and apartment share."),
    "network": (0.15, "Savomart network fit", "Distance to nearest Savomart: too close cannibalises, too far strains supply."),
    "access": (0.10, "Access & visibility", "Road density and length of arterial roads."),
}

# metrics that have a city-wide distribution (built by scripts/build_baseline.py)
DIST_METRICS = ["pop_density", "people_per_outlet", "supermarkets_per_10k", "generators_per_km2",
                "affluence_per_km2", "apartment_share", "road_density", "major_road_density"]

BANDS = [(70, "Strong fit"), (55, "Promising"), (40, "Marginal"), (0, "Weak fit")]


class Distributions:
    def __init__(self, dists: dict[str, list[float]]):
        self.d = {k: sorted(v) for k, v in dists.items()}

    @classmethod
    def load(cls, db: Session) -> "Distributions":
        row = db.get(BaselineMeta, "distributions")
        return cls(row.value if row else {})

    def pct(self, metric: str, value: float) -> float:
        arr = self.d.get(metric)
        if not arr:
            return 50.0
        lo = bisect.bisect_left(arr, value)
        hi = bisect.bisect_right(arr, value)
        return round(100.0 * ((lo + hi) / 2) / len(arr), 1)


def network_score(nearest_km: float | None) -> float:
    """Piecewise-linear preference over distance to the nearest Savomart store.

    < 1 km   : heavy cannibalisation of an existing store
    2–5 km   : sweet spot — new catchment, but inside the existing supply/ops cluster
    > 15 km  : a new cluster; viable but costlier to supply and supervise
    """
    if nearest_km is None:
        return 50.0
    pts = [(0, 0), (1.0, 15), (2.0, 70), (2.5, 100), (5.0, 100), (8.0, 80), (15.0, 60), (40.0, 45)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if nearest_km <= x1:
            return round(y0 + (y1 - y0) * (nearest_km - x0) / (x1 - x0), 1)
    return 45.0


def score(metrics: dict, dist: Distributions) -> dict:
    """Return pillars, overall score, band and an itemised indicator table."""
    p = dist.pct
    indicators = [
        _ind("pop_density", "Estimated residents / km²", metrics["pop_density"], "people/km²", "demand",
             p("pop_density", metrics["pop_density"]),
             "OSM buildings + residential roads, calibrated to Census 2011 (dasymetric estimate)"),
        _ind("people_per_outlet", "Residents per grocery outlet", metrics["people_per_outlet"], "people", "gap",
             p("people_per_outlet", metrics["people_per_outlet"]),
             "OSM shop=supermarket/convenience/grocery/greengrocer… (OSM under-counts kiranas; relative signal)"),
        _ind("supermarkets_per_10k", "Supermarkets per 10k residents", metrics["supermarkets_per_10k"], "per 10k",
             "gap", 100 - p("supermarkets_per_10k", metrics["supermarkets_per_10k"]),
             "OSM shop=supermarket/department_store; lower is better (inverted percentile)"),
        _ind("generators_per_km2", "Footfall generators / km²", metrics["generators_per_km2"], "per km²",
             "activity", p("generators_per_km2", metrics["generators_per_km2"]),
             "OSM schools, colleges, clinics, pharmacies, transit stops, worship, offices, markets"),
        _ind("affluence_per_km2", "Banks, eateries & malls / km²", metrics["affluence_per_km2"], "per km²",
             "spending", p("affluence_per_km2", metrics["affluence_per_km2"]), "OSM amenity=bank/atm/restaurant/cafe, shop=mall"),
        _ind("apartment_share", "Apartment share of homes", round(metrics["apartment_share"] * 100, 1), "%",
             "spending", p("apartment_share", metrics["apartment_share"]), "OSM building=apartments vs other residential"),
        _ind("nearest_store_km", "Nearest Savomart store", metrics["nearest_store_km"], "km", "network",
             network_score(metrics["nearest_store_km"]), "Savomart Stores API (operational stores)"),
        _ind("road_density", "Road density", metrics["road_density"], "km/km²", "access",
             p("road_density", metrics["road_density"]), "OSM highway=* (drivable)"),
        _ind("major_road_density", "Arterial roads", metrics["major_road_density"], "km/km²", "access",
             p("major_road_density", metrics["major_road_density"]), "OSM trunk/primary/secondary"),
    ]
    by_pillar: dict[str, list[float]] = {}
    ind_weight = {"people_per_outlet": 0.6, "supermarkets_per_10k": 0.4, "affluence_per_km2": 0.6,
                  "apartment_share": 0.4, "road_density": 0.5, "major_road_density": 0.5}
    for ind in indicators:
        w = ind_weight.get(ind["key"], 1.0)
        ind["weight_in_pillar"] = w
        by_pillar.setdefault(ind["pillar"], []).append((ind["score"], w))
    pillars = {}
    total = 0.0
    for key, (w, label, desc) in PILLARS.items():
        vals = by_pillar.get(key, [])
        sw = sum(x[1] for x in vals) or 1
        val = round(sum(x[0] * x[1] for x in vals) / sw, 1) if vals else 50.0
        contribution = round(val * w, 1)
        total += contribution
        pillars[key] = {"label": label, "description": desc, "score": val, "weight": w,
                        "contribution": contribution}
    total = round(total, 1)
    return {"score": total, "band": band(total), "pillars": pillars, "indicators": indicators,
            "model_version": MODEL_VERSION}


def band(s: float) -> str:
    for threshold, label in BANDS:
        if s >= threshold:
            return label
    return BANDS[-1][1]


def _ind(key, label, value, unit, pillar, pct, source) -> dict:
    return {"key": key, "label": label, "value": value, "unit": unit, "pillar": pillar,
            "score": round(float(pct), 1), "source": source}


def confidence(metrics: dict) -> tuple[str, list[str]]:
    """How much should a manager trust this? Driven by data completeness, not by the score."""
    reasons = []
    level = 3
    if metrics["data_coverage"] < 0.5:
        level -= 1
        reasons.append(f"Only {round(metrics['data_coverage'] * 100)}% of the area has any mapped data in OSM.")
    if metrics["buildings"] < 50 * max(metrics["area_km2"], 0.1):
        level -= 1
        reasons.append("Few buildings are mapped in OSM here, so population leans on the road-network proxy.")
    if metrics["population"] < 5000:
        level -= 1
        reasons.append("Small resident base — percentiles are sensitive to a handful of POIs.")
    if not reasons:
        reasons.append("Good OSM coverage of buildings, roads and amenities in this area.")
    return (["Low", "Low", "Medium", "High"][max(level, 0)], reasons)
