"""Feature extraction over sets of H3 cells.

Everything is built on *additive* aggregates (sums per res-9 cell), so the same
code produces features for an area report, a hotspot's walking catchment,
a property's catchment and every cell of the city-wide opportunity map.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import geo
from ..models import CellStat, Poi, Road, Store

POI_CATEGORIES = [
    "supermarket", "grocery", "fresh_food", "mall", "school", "college", "healthcare", "pharmacy",
    "bank", "food", "worship", "market", "transit", "office", "fuel", "leisure", "retail",
]
GROCERY = ("supermarket", "grocery", "fresh_food")
GENERATORS = ("school", "college", "healthcare", "pharmacy", "transit", "worship", "market", "office", "mall")
AFFLUENCE = ("bank", "food", "mall", "leisure")

SUM_FIELDS = ["buildings", "res_buildings", "apartments", "commercial_buildings", "road_m", "res_road_m",
              "major_road_m", "est_population", "est_households"]


@dataclass
class Agg:
    area_km2: float = 0.0
    sums: dict[str, float] = field(default_factory=lambda: {k: 0.0 for k in SUM_FIELDS})
    pois: dict[str, int] = field(default_factory=lambda: {k: 0 for k in POI_CATEGORIES})
    n_cells: int = 0
    n_cells_with_data: int = 0

    def add_cell(self, cs: CellStat | None, area_km2: float) -> None:
        self.area_km2 += area_km2
        self.n_cells += 1
        if cs is None:
            return
        self.n_cells_with_data += 1
        for k in SUM_FIELDS:
            self.sums[k] += getattr(cs, k) or 0
        for k, v in (cs.poi_counts or {}).items():
            if k in self.pois:
                self.pois[k] += v

    def merge(self, other: "Agg") -> None:
        self.area_km2 += other.area_km2
        self.n_cells += other.n_cells
        self.n_cells_with_data += other.n_cells_with_data
        for k in SUM_FIELDS:
            self.sums[k] += other.sums[k]
        for k in POI_CATEGORIES:
            self.pois[k] += other.pois[k]


def load_cellstats(db: Session, cells9: Iterable[str]) -> dict[str, CellStat]:
    cells9 = list(cells9)
    out: dict[str, CellStat] = {}
    for i in range(0, len(cells9), 900):  # SQLite variable limit
        chunk = cells9[i:i + 900]
        for cs in db.scalars(select(CellStat).where(CellStat.h3_9.in_(chunk))):
            out[cs.h3_9] = cs
    return out


def aggregate(db: Session, cells9: Iterable[str], cache: dict[str, CellStat] | None = None) -> Agg:
    cells9 = list(dict.fromkeys(cells9))
    stats = cache if cache is not None else load_cellstats(db, cells9)
    agg = Agg()
    for c in cells9:
        agg.add_cell(stats.get(c), geo.cell_area_km2(c))
    return agg


# ------------------------------------------------------------------ Savomart network

def chennai_stores(db: Session) -> list[Store]:
    return list(db.scalars(select(Store).where(Store.is_operational.is_(True))))


def nearest_stores(stores: list[Store], lat: float, lng: float, n: int = 3) -> list[dict]:
    ds = sorted(((geo.haversine_m(lat, lng, s.lat, s.lng), s) for s in stores), key=lambda x: x[0])
    return [{"store_code": s.store_code, "name": s.name, "lat": s.lat, "lng": s.lng,
             "distance_km": round(d / 1000, 2)} for d, s in ds[:n]]


# ------------------------------------------------------------------ derived metrics

def derive(agg: Agg, lat: float, lng: float, stores: list[Store]) -> dict:
    """Turn raw sums into the named metrics that scoring uses. Pure function (testable)."""
    a = max(agg.area_km2, 1e-6)
    s, p = agg.sums, agg.pois
    pop = s["est_population"]
    grocery = sum(p[k] for k in GROCERY)
    generators = sum(p[k] for k in GENERATORS)
    affluence = p["bank"] + p["food"] + 5 * p["mall"] + p["leisure"]
    res_b = max(s["res_buildings"], 1)
    near = nearest_stores(stores, lat, lng, 3)
    return {
        "area_km2": round(a, 2),
        "population": round(pop),
        "households": round(s["est_households"]),
        "pop_density": round(pop / a),
        "buildings": int(s["buildings"]),
        "apartment_share": round(s["apartments"] / res_b, 3) if s["res_buildings"] else 0.0,
        "grocery_outlets": grocery,
        "supermarkets": p["supermarket"],
        "people_per_outlet": round(pop / (grocery + 1)),
        "supermarkets_per_10k": round(p["supermarket"] / max(pop / 10000, 0.1), 2),
        "generators": generators,
        "generators_per_km2": round(generators / a, 2),
        "affluence_per_km2": round(affluence / a, 2),
        "road_km": round(s["road_m"] / 1000, 1),
        "road_density": round(s["road_m"] / 1000 / a, 2),
        "major_road_density": round(s["major_road_m"] / 1000 / a, 2),
        "pois": dict(p),
        "nearest_stores": near,
        "nearest_store_km": near[0]["distance_km"] if near else None,
        "data_coverage": round(agg.n_cells_with_data / max(agg.n_cells, 1), 2),
    }


# ------------------------------------------------------------------ point lookups

def pois_near(db: Session, lat: float, lng: float, radius_m: float,
              categories: Iterable[str] | None = None, limit: int | None = None) -> list[dict]:
    cells = geo.covering_cells(lat, lng, radius_m, 9)
    q = select(Poi).where(Poi.h3_9.in_(cells))
    if categories:
        q = q.where(Poi.category.in_(list(categories)))
    out = []
    for poi in db.scalars(q):
        d = geo.haversine_m(lat, lng, poi.lat, poi.lng)
        if d <= radius_m:
            out.append({"id": poi.id, "name": poi.name, "brand": poi.brand, "category": poi.category,
                        "tag": poi.tag, "lat": poi.lat, "lng": poi.lng, "distance_m": round(d)})
    out.sort(key=lambda x: x["distance_m"])
    return out[:limit] if limit else out


def nearest_road(db: Session, lat: float, lng: float, radius_m: float = 120) -> dict | None:
    cells = geo.covering_cells(lat, lng, radius_m, 9)
    best = None
    for r in db.scalars(select(Road).where(Road.h3_9.in_(cells))):
        d = min(_point_segment_m(lat, lng, a, b) for a, b in zip(r.coords, r.coords[1:]))
        if d <= radius_m and (best is None or d < best[0]):
            best = (d, r)
    if not best:
        return None
    d, r = best
    return {"name": r.name, "highway": r.highway, "distance_m": round(d)}


def _point_segment_m(lat: float, lng: float, a: list[float], b: list[float]) -> float:
    # local equirectangular projection is accurate enough at <1 km scales
    import math
    kx = 111320 * math.cos(math.radians(lat))
    ky = 110540
    px, py = 0.0, 0.0
    ax, ay = (a[0] - lng) * kx, (a[1] - lat) * ky
    bx, by = (b[0] - lng) * kx, (b[1] - lat) * ky
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(cx - px, cy - py)
