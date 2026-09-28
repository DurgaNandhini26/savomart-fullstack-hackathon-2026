"""Ingest OpenStreetMap data for the Chennai Metropolitan Area via Overpass.

What we pull and why:
  * POIs (shops, amenities, transit, offices)  -> demand generators & competition
  * place=* nodes                               -> locality search
  * highways with geometry                      -> road access, lane-level survey units
  * building centroids (+ building type)        -> residential density for population estimates

All raw responses are cached (data/raw/overpass) so reruns are cheap and the
exact OSM snapshot timestamp is recorded in data_snapshots.
"""
from __future__ import annotations

import csv
import io
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete  # noqa: E402

from app import geo  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import DataSnapshot, Place, Poi, Road  # noqa: E402
from scripts.overpass import osm_timestamp, query, tiles  # noqa: E402

BBOX = geo.CHENNAI_BBOX

AMENITIES = (
    "school|kindergarten|college|university|hospital|clinic|doctors|pharmacy|dentist|bank|atm|"
    "restaurant|cafe|fast_food|place_of_worship|marketplace|bus_station|fuel|cinema|community_centre"
)
ROAD_TYPES = (
    "trunk|primary|secondary|tertiary|unclassified|residential|living_street|"
    "trunk_link|primary_link|secondary_link|tertiary_link|road"
)
MAJOR_ROADS = {"trunk", "primary", "secondary", "trunk_link", "primary_link", "secondary_link"}
RES_ROADS = {"residential", "living_street", "unclassified"}

# Our POI taxonomy. Order matters: first match wins.
SUPERMARKET_BRANDS = ("reliance", "more", "dmart", "d-mart", "nilgiris", "spencer", "star bazaar",
                      "big bazaar", "ratnadeep", "heritage", "grace", "kannan", "jiomart", "smart point",
                      "savomart", "zepto", "blinkit", "swiggy")


def categorize(tags: dict) -> str | None:
    shop, amen = tags.get("shop"), tags.get("amenity")
    if shop in ("supermarket", "department_store", "hypermarket", "wholesale"):
        return "supermarket"
    if shop in ("convenience", "grocery", "general", "variety_store", "kiosk"):
        return "grocery"
    if shop in ("greengrocer", "bakery", "butcher", "dairy", "seafood", "deli", "frozen_food",
                "spices", "rice", "confectionery", "beverages"):
        return "fresh_food"
    if shop == "mall":
        return "mall"
    if amen in ("school", "kindergarten"):
        return "school"
    if amen in ("college", "university"):
        return "college"
    if amen in ("hospital", "clinic", "doctors", "dentist"):
        return "healthcare"
    if amen == "pharmacy" or shop == "chemist":
        return "pharmacy"
    if amen in ("bank", "atm"):
        return "bank"
    if amen in ("restaurant", "cafe", "fast_food"):
        return "food"
    if amen == "place_of_worship":
        return "worship"
    if amen == "marketplace":
        return "market"
    if amen in ("bus_station",) or tags.get("highway") == "bus_stop" or tags.get("railway") in ("station", "halt") \
            or tags.get("public_transport") == "station":
        return "transit"
    if tags.get("office"):
        return "office"
    if amen == "fuel":
        return "fuel"
    if amen in ("cinema", "community_centre"):
        return "leisure"
    if shop:
        return "retail"
    return None


def raw_tag(tags: dict) -> str:
    for k in ("shop", "amenity", "railway", "highway", "office", "public_transport"):
        if k in tags:
            return f"{k}={tags[k]}"[:60]
    return "?"


# ------------------------------------------------------------------ POIs

def ingest_pois(db) -> str | None:
    print("-> POIs")
    seen: dict[str, Poi] = {}
    ts = None
    for i, t in enumerate(tiles(BBOX, 3, 2)):
        b = ",".join(map(str, t))
        ql = f"""[out:json][timeout:180];
(
  nwr["shop"]({b});
  nwr["amenity"~"^({AMENITIES})$"]({b});
  node["highway"="bus_stop"]({b});
  nwr["railway"~"^(station|halt)$"]({b});
  nwr["office"]({b});
);
out center tags;"""
        data = query(ql, name=f"pois_{i}")
        ts = osm_timestamp(data) or ts
        for el in data.get("elements", []):
            tags = el.get("tags") or {}
            cat = categorize(tags)
            if not cat:
                continue
            if el["type"] == "node":
                lat, lng = el["lat"], el["lon"]
            elif "center" in el:
                lat, lng = el["center"]["lat"], el["center"]["lon"]
            else:
                continue
            if not geo.in_chennai(lat, lng):
                continue
            ref = f"{el['type'][0]}{el['id']}"
            if ref in seen:
                continue
            seen[ref] = Poi(
                osm_ref=ref, category=cat, tag=raw_tag(tags),
                name=(tags.get("name:en") or tags.get("name") or None),
                brand=tags.get("brand") or None,
                lat=lat, lng=lng,
                h3_9=geo.cell(lat, lng, 9), h3_8=geo.cell(lat, lng, 8),
            )
        print(f"   tile {i}: {len(seen)} POIs so far", flush=True)
    db.execute(delete(Poi))
    db.add_all(seen.values())
    db.add(DataSnapshot(source="osm_pois", source_timestamp=ts, record_count=len(seen),
                        notes="Overpass API; shops, amenities, transit, offices"))
    db.commit()
    return ts


# ------------------------------------------------------------------ places

def ingest_places(db) -> None:
    print("-> places")
    b = ",".join(map(str, BBOX))
    ql = f"""[out:json][timeout:120];
node["place"~"^(suburb|neighbourhood|quarter|town|village|locality)$"]({b});
out body;"""
    data = query(ql, name="places")
    db.execute(delete(Place).where(Place.kind == "locality"))
    n = 0
    seen = set()
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name:en") or tags.get("name")
        if not name or not geo.in_chennai(el["lat"], el["lon"]):
            continue
        key = (name.lower(), round(el["lat"], 3), round(el["lon"], 3))
        if key in seen:
            continue
        seen.add(key)
        db.add(Place(kind="locality", name=name, place_type=tags.get("place"),
                     pincode=tags.get("postal_code") or tags.get("addr:postcode"),
                     lat=el["lat"], lng=el["lon"], source="osm"))
        n += 1
    db.add(DataSnapshot(source="osm_places", source_timestamp=osm_timestamp(data), record_count=n))
    db.commit()
    print(f"   {n} localities")


# ------------------------------------------------------------------ roads

def _densify(coords: list[list[float]], step_m: float = 40.0) -> list[list[float]]:
    out = [coords[0]]
    for a, b in zip(coords, coords[1:]):
        d = geo.haversine_m(a[1], a[0], b[1], b[0])
        n = max(1, math.ceil(d / step_m))
        for k in range(1, n + 1):
            f = k / n
            out.append([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f])
    return out


def split_by_cell(coords: list[list[float]]) -> list[tuple[str, list[list[float]]]]:
    """Split a polyline into runs that each lie in one H3 res-9 cell (by vertex)."""
    pts = _densify(coords)
    runs: list[tuple[str, list[list[float]]]] = []
    cur_cell, cur = None, []
    for p in pts:
        c = geo.cell(p[1], p[0], 9)
        if c != cur_cell and cur:
            cur.append(p)  # close the run at the boundary point so geometry stays continuous
            runs.append((cur_cell, cur))
            cur = [p]
        else:
            cur.append(p)
        cur_cell = c
    if len(cur) >= 2:
        runs.append((cur_cell, cur))
    return runs


def _simplify(coords: list[list[float]]) -> list[list[float]]:
    # drop densified interior points that are nearly collinear (keeps payloads small)
    if len(coords) <= 2:
        return [[round(x, 6), round(y, 6)] for x, y in coords]
    out = [coords[0]]
    for i in range(1, len(coords) - 1):
        a, b, c = out[-1], coords[i], coords[i + 1]
        cross = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        if cross > 1e-10:
            out.append(b)
    out.append(coords[-1])
    return [[round(x, 6), round(y, 6)] for x, y in out]


def ingest_roads(db) -> None:
    print("-> roads")
    seen: set[int] = set()
    rows: list[Road] = []
    ts = None
    for i, t in enumerate(tiles(BBOX, 3, 2)):
        b = ",".join(map(str, t))
        ql = f"""[out:json][timeout:180];
way["highway"~"^({ROAD_TYPES})$"]({b});
out tags geom;"""
        data = query(ql, name=f"roads_{i}")
        ts = osm_timestamp(data) or ts
        for el in data.get("elements", []):
            if el["id"] in seen or "geometry" not in el:
                continue
            seen.add(el["id"])
            tags = el.get("tags") or {}
            coords = [[p["lon"], p["lat"]] for p in el["geometry"] if p]
            if len(coords) < 2:
                continue
            for seg, (c9, run) in enumerate(split_by_cell(coords)):
                clat, clng = run[len(run) // 2][1], run[len(run) // 2][0]
                if not geo.in_chennai(clat, clng):
                    continue
                length = geo.line_length_m(run)
                if length < 5:
                    continue
                rows.append(Road(
                    osm_id=el["id"], seg=seg, name=tags.get("name:en") or tags.get("name"),
                    highway=tags.get("highway", "road"), length_m=round(length, 1),
                    coords=_simplify(run), mid_lat=clat, mid_lng=clng,
                    h3_9=c9, h3_8=geo.cell(clat, clng, 8),
                ))
        print(f"   tile {i}: {len(seen)} ways -> {len(rows)} segments", flush=True)
    db.execute(delete(Road))
    for k in range(0, len(rows), 20000):
        db.add_all(rows[k:k + 20000])
        db.flush()
    db.add(DataSnapshot(source="osm_roads", source_timestamp=ts, record_count=len(rows),
                        notes=f"{len(seen)} OSM ways split into H3-res9 segments"))
    db.commit()


# ------------------------------------------------------------------ buildings

RES_BUILDINGS = {"house", "residential", "apartments", "detached", "semidetached_house", "terrace",
                 "bungalow", "dormitory", "hut", "flats"}
COM_BUILDINGS = {"commercial", "retail", "office", "supermarket", "kiosk", "shop", "hotel", "mall"}


def building_counts() -> tuple[dict[str, dict[str, int]], str | None]:
    """Building centroids aggregated to H3 res-9: {cell: {total, res, apt, com}}."""
    print("-> buildings")
    agg: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "res": 0, "apt": 0, "com": 0})
    ts = None
    for i, t in enumerate(tiles(BBOX, 4, 3)):
        b = ",".join(map(str, t))
        ql = f"""[out:csv(::id,::lat,::lon,building;false;",")][timeout:180];
way["building"]({b});
out center;"""
        text = query(ql, name=f"buildings_{i}", fmt="csv")
        n = 0
        for row in csv.reader(io.StringIO(text)):
            if len(row) < 4 or not row[1]:
                continue
            try:
                lat, lng = float(row[1]), float(row[2])
            except ValueError:
                continue
            # the tile query is by bbox intersection; count each building only in its own tile
            if not (t[0] <= lat < t[2] and t[1] <= lng < t[3]):
                continue
            kind = row[3].strip().lower()
            a = agg[geo.cell(lat, lng, 9)]
            a["total"] += 1
            if kind in RES_BUILDINGS:
                a["res"] += 1
            if kind == "apartments":
                a["apt"] += 1
            if kind in COM_BUILDINGS:
                a["com"] += 1
            n += 1
        print(f"   tile {i}: {n} buildings", flush=True)
    return agg, ts


if __name__ == "__main__":
    from app.db import Base, engine
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        what = sys.argv[1:] or ["pois", "places", "roads"]
        if "pois" in what:
            ingest_pois(s)
        if "places" in what:
            ingest_places(s)
        if "roads" in what:
            ingest_roads(s)
        if "buildings" in what:
            counts, _ = building_counts()
            print(len(counts), "cells with buildings")
