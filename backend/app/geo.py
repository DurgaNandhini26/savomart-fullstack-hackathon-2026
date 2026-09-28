"""Geo helpers built on H3 (Uber's hexagonal grid) + haversine."""
import math
from collections.abc import Iterable

import h3

# Chennai Metropolitan Area working bounding box (south, west, north, east).
CHENNAI_BBOX = (12.78, 79.98, 13.32, 80.34)
CHENNAI_CENTER = (13.0500, 80.2300)

RES_AREA = 8    # "area" grid shown on the map: ~0.74 km² hexagons
RES_FINE = 9    # fine grid for hotspots, catchments and survey splitting: ~0.105 km²

EARTH_R = 6371008.8


def in_chennai(lat: float, lng: float) -> bool:
    s, w, n, e = CHENNAI_BBOX
    return s <= lat <= n and w <= lng <= e


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def line_length_m(coords: list[list[float]]) -> float:
    """coords are [lng, lat] pairs (GeoJSON order)."""
    return sum(
        haversine_m(a[1], a[0], b[1], b[0]) for a, b in zip(coords, coords[1:])
    )


def cell(lat: float, lng: float, res: int = RES_FINE) -> str:
    return h3.latlng_to_cell(lat, lng, res)


def cell_center(c: str) -> tuple[float, float]:
    return h3.cell_to_latlng(c)


def cell_area_km2(c: str) -> float:
    return h3.cell_area(c, unit="km^2")


def cells_area_km2(cells: Iterable[str]) -> float:
    return sum(cell_area_km2(c) for c in cells)


def cell_boundary_geojson(c: str) -> list[list[float]]:
    ring = [[lng, lat] for lat, lng in h3.cell_to_boundary(c)]
    ring.append(ring[0])
    return ring


def cells_to_feature_collection(cells: Iterable[str], props: dict[str, dict] | None = None) -> dict:
    feats = []
    for c in cells:
        feats.append({
            "type": "Feature",
            "id": c,
            "properties": {"h3": c, **((props or {}).get(c, {}))},
            "geometry": {"type": "Polygon", "coordinates": [cell_boundary_geojson(c)]},
        })
    return {"type": "FeatureCollection", "features": feats}


def cells_outline(cells: Iterable[str]) -> dict:
    """Merged outline of a cell set as a GeoJSON (Multi)Polygon geometry."""
    shape = h3.cells_to_h3shape(list(cells))
    return shape.__geo_interface__


def disk_cells(lat: float, lng: float, radius_m: float, res: int = RES_FINE) -> list[str]:
    """All cells at `res` whose centre lies within radius_m of the point."""
    origin = h3.latlng_to_cell(lat, lng, res)
    edge = h3.average_hexagon_edge_length(res, unit="m")
    k = max(1, math.ceil(radius_m / (edge * 1.5)) + 1)
    out = []
    for c in h3.grid_disk(origin, k):
        clat, clng = h3.cell_to_latlng(c)
        if haversine_m(lat, lng, clat, clng) <= radius_m:
            out.append(c)
    if origin not in out:
        out.append(origin)
    return out


def covering_cells(lat: float, lng: float, radius_m: float, res: int) -> list[str]:
    """Cells at `res` that could contain any point within radius_m (superset, for index lookups)."""
    origin = h3.latlng_to_cell(lat, lng, res)
    edge = h3.average_hexagon_edge_length(res, unit="m")
    k = max(1, math.ceil(radius_m / (edge * 1.5)) + 1)
    return list(h3.grid_disk(origin, k))


def children(cells: Iterable[str], res: int = RES_FINE) -> list[str]:
    out: list[str] = []
    for c in cells:
        if h3.get_resolution(c) == res:
            out.append(c)
        else:
            out.extend(h3.cell_to_children(c, res))
    return out


def polygon_to_cells(geojson_geom: dict, res: int) -> list[str]:
    shape = h3.geo_to_h3shape(geojson_geom)
    return list(h3.h3shape_to_cells(shape, res))


def centroid_of_cells(cells: Iterable[str]) -> tuple[float, float]:
    pts = [h3.cell_to_latlng(c) for c in cells]
    if not pts:
        return CHENNAI_CENTER
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def cells_in_bbox(south: float, west: float, north: float, east: float, res: int = RES_AREA) -> list[str]:
    geom = {
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    }
    return polygon_to_cells(geom, res)
