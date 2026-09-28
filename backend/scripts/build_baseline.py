"""Build the city baseline from ingested public data.

1. Aggregate POIs, roads and building centroids per H3 res-9 cell.
2. Estimate residents per cell with *dasymetric allocation*: a calibration total from
   the Census is spread across cells in proportion to residential signals we can see in OSM
   (residential-looking buildings and residential street length). Both signals are used
   because OSM building completeness in Chennai is patchy, while the street network is
   close to complete.
3. Compute city-wide distributions of every scoring metric over ~1.5 km neighbourhoods
   (a res-8 cell + its ring) — these turn raw numbers into percentiles.
4. Score every populated res-8 neighbourhood -> the city-wide opportunity map.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import h3  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app import geo  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import BaselineMeta, CellStat, DataSnapshot, OpportunityCell, Place, Poi, Road  # noqa: E402
from app.services import features as F  # noqa: E402
from app.services import scoring as S  # noqa: E402

# --- Calibration (documented in README) -------------------------------------------------
# Census of India 2011: Chennai Urban Agglomeration ≈ 8.65 million residents. Our bounding box
# is a little larger than the UA (includes peri-urban fringe), so we calibrate to 9.0 M.
# Average household size ≈ 4.0 (Census 2011, Chennai district: 4.65 M people / ~1.15 M households).
# POP_GROWTH lets you project forward; we keep 1.0 and label estimates "2011-calibrated".
CALIBRATION_POPULATION = 9_000_000
HOUSEHOLD_SIZE = 4.0
POP_GROWTH = 1.0
UNKNOWN_BUILDING_RES_SHARE = 0.7   # building=yes: share assumed residential in Indian urban fabric
W_BUILDINGS, W_ROADS = 0.5, 0.5


def main() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    print("-> aggregating per H3 res-9 cell")
    cells: dict[str, dict] = defaultdict(lambda: {
        "buildings": 0, "res_buildings": 0, "apartments": 0, "commercial_buildings": 0,
        "road_m": 0.0, "res_road_m": 0.0, "major_road_m": 0.0, "poi": defaultdict(int)})

    for c9, cat in db.execute(select(Poi.h3_9, Poi.category)):
        cells[c9]["poi"][cat] += 1
    for c9, hw, length in db.execute(select(Road.h3_9, Road.highway, Road.length_m)):
        c = cells[c9]
        c["road_m"] += length
        if hw in ("residential", "living_street", "unclassified"):
            c["res_road_m"] += length
        if hw in ("trunk", "primary", "secondary", "trunk_link", "primary_link", "secondary_link"):
            c["major_road_m"] += length

    has_buildings = False
    try:
        from scripts.ingest_osm import building_counts
        bcounts, _ = building_counts()
        for c9, b in bcounts.items():
            c = cells[c9]
            c["buildings"] = b["total"]
            c["res_buildings"] = b["res"]
            c["apartments"] = b["apt"]
            c["commercial_buildings"] = b["com"]
        has_buildings = bool(bcounts)
        db.add(DataSnapshot(source="osm_buildings", record_count=sum(b["total"] for b in bcounts.values()),
                            notes="building centroids aggregated to H3 res-9"))
    except Exception as exc:  # noqa: BLE001
        print(f"   ! building footprints unavailable ({exc!r}); population will use roads only")

    # -------------------------------------------------- dasymetric population
    def res_building_signal(c):
        unknown = max(c["buildings"] - c["res_buildings"] - c["commercial_buildings"], 0)
        return c["res_buildings"] + UNKNOWN_BUILDING_RES_SHARE * unknown

    sum_b = sum(res_building_signal(c) for c in cells.values()) or 1
    sum_r = sum(c["res_road_m"] for c in cells.values()) or 1
    wb, wr = (W_BUILDINGS, W_ROADS) if has_buildings else (0.0, 1.0)
    total = CALIBRATION_POPULATION * POP_GROWTH

    db.execute(delete(CellStat))
    rows = []
    for c9, c in cells.items():
        share = wb * res_building_signal(c) / sum_b + wr * c["res_road_m"] / sum_r
        pop = total * share
        lat, lng = h3.cell_to_latlng(c9)
        rows.append(CellStat(
            h3_9=c9, h3_8=h3.cell_to_parent(c9, 8), lat=lat, lng=lng,
            buildings=c["buildings"], res_buildings=c["res_buildings"], apartments=c["apartments"],
            commercial_buildings=c["commercial_buildings"], road_m=round(c["road_m"], 1),
            res_road_m=round(c["res_road_m"], 1), major_road_m=round(c["major_road_m"], 1),
            est_population=round(pop, 1), est_households=round(pop / HOUSEHOLD_SIZE, 1),
            poi_counts=dict(c["poi"]),
        ))
    db.add_all(rows)
    db.commit()
    print(f"   {len(rows)} res-9 cells, population allocated: {round(sum(r.est_population for r in rows)):,}")

    # -------------------------------------------------- neighbourhood distributions (res-8 + ring)
    print("-> city-wide distributions & opportunity map")
    stats = {r.h3_9: r for r in rows}
    by8: dict[str, F.Agg] = defaultdict(F.Agg)
    for c9, cs in stats.items():
        by8[cs.h3_8].add_cell(cs, geo.cell_area_km2(c9))
    # cells without data still have area
    for c8, agg in by8.items():
        missing = 7 - agg.n_cells  # res-8 has 7 res-9 children
        if missing > 0:
            agg.area_km2 += missing * geo.cell_area_km2(next(iter(h3.cell_to_children(c8, 9))))
            agg.n_cells += missing

    stores = F.chennai_stores(db)
    neighbourhoods: dict[str, dict] = {}
    for c8 in by8:
        ring = F.Agg()
        for n8 in h3.grid_disk(c8, 1):
            if n8 in by8:
                ring.merge(by8[n8])
            else:
                ring.area_km2 += geo.cell_area_km2(n8)
                ring.n_cells += 7
        lat, lng = h3.cell_to_latlng(c8)
        m = F.derive(ring, lat, lng, stores)
        # "normal" is defined by urban neighbourhoods (>= ~1,500 residents/km² over the ~5 km² ring),
        # otherwise every part of the core city looks top-decile against rural fringe cells
        if m["population"] >= 8000:
            neighbourhoods[c8] = m

    dists = {k: [m[k] for m in neighbourhoods.values()] for k in S.DIST_METRICS}
    meta = db.get(BaselineMeta, "distributions")
    if meta:
        meta.value = dists
    else:
        db.add(BaselineMeta(key="distributions", value=dists))
    info = {"calibration_population": CALIBRATION_POPULATION, "household_size": HOUSEHOLD_SIZE,
            "pop_growth": POP_GROWTH, "neighbourhoods": len(neighbourhoods), "used_buildings": has_buildings,
            "model_version": S.MODEL_VERSION}
    meta2 = db.get(BaselineMeta, "info")
    if meta2:
        meta2.value = info
    else:
        db.add(BaselineMeta(key="info", value=info))
    db.flush()

    distobj = S.Distributions(dists)
    localities = [(p.name, p.lat, p.lng) for p in db.scalars(select(Place).where(Place.kind == "locality",
                                                                                Place.place_type.in_(["suburb", "neighbourhood", "quarter", "town", "village"])))]
    db.execute(delete(OpportunityCell))
    for c8, m in neighbourhoods.items():
        sc = S.score(m, distobj)
        lat, lng = h3.cell_to_latlng(c8)
        loc = min(localities, key=lambda x: geo.haversine_m(lat, lng, x[1], x[2]))[0] if localities else None
        db.add(OpportunityCell(
            h3_8=c8, lat=lat, lng=lng, score=sc["score"], locality=loc,
            pillars={k: v["score"] for k, v in sc["pillars"].items()},
            features={k: m[k] for k in ("population", "pop_density", "grocery_outlets", "supermarkets",
                                        "people_per_outlet", "nearest_store_km", "generators")},
        ))
    db.add(DataSnapshot(source="baseline", record_count=len(neighbourhoods),
                        notes=f"{S.MODEL_VERSION}; calibration {CALIBRATION_POPULATION:,}"))
    db.commit()
    print(f"   {len(neighbourhoods)} populated neighbourhoods scored")
    db.close()


if __name__ == "__main__":
    main()
