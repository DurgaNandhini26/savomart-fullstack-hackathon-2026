"""Resolve a BD manager's selection (pincode / locality / grid cells) into H3 res-8 cells.

Pincode and locality boundaries are not reliably available as open polygons, so an
area is approximated as the grid cells *closest* to that pincode's / locality's
centroid (a discrete Voronoi partition), capped at a max radius. This yields
non-overlapping, gap-free areas that tile the city.
"""
from __future__ import annotations

import h3
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import geo
from ..models import Place

LOCALITY_TYPES = ["suburb", "neighbourhood", "quarter", "town", "village"]
MAX_RADIUS_M = {"pincode": 4500, "suburb": 2500, "town": 3000, "village": 1800, "neighbourhood": 1500,
                "quarter": 1500, "locality": 1200}


class AreaError(ValueError):
    pass


def _voronoi_cells(target: Place, rivals: list[Place], max_radius: float) -> list[str]:
    out = []
    for c in geo.covering_cells(target.lat, target.lng, max_radius, geo.RES_AREA):
        lat, lng = h3.cell_to_latlng(c)
        d_t = geo.haversine_m(lat, lng, target.lat, target.lng)
        if d_t > max_radius:
            continue
        if all(d_t <= geo.haversine_m(lat, lng, r.lat, r.lng) for r in rivals if r.id != target.id):
            out.append(c)
    if len(out) < 3:  # tiny Voronoi cell (dense neighbourhoods): fall back to a 1 km disk
        out = geo.disk_cells(target.lat, target.lng, 1000, geo.RES_AREA)
    return out


def resolve(db: Session, selection_type: str, value: str | None, cells: list[str] | None) -> dict:
    if selection_type == "cells":
        cells = [c for c in (cells or []) if h3.is_valid_cell(c)]
        if not cells:
            raise AreaError("Select at least one grid cell on the map.")
        if len(cells) > 60:
            raise AreaError("Please select at most 60 cells (~45 km²) per analysis.")
        cells = [c if h3.get_resolution(c) == geo.RES_AREA else h3.cell_to_parent(c, geo.RES_AREA) for c in cells]
        cells = list(dict.fromkeys(cells))
        lat, lng = geo.centroid_of_cells(cells)
        if not geo.in_chennai(lat, lng):
            raise AreaError("Selected cells are outside the Chennai region.")
        name = f"{nearest_locality(db, lat, lng) or 'Custom area'} (custom {len(cells)} cells)"
        return {"cells": cells, "name": name, "input": f"{len(cells)} cells"}

    if selection_type == "pincode":
        pin = (value or "").strip()
        place = db.scalar(select(Place).where(Place.kind == "pincode", Place.pincode == pin))
        if not place:
            raise AreaError(f"Pincode {pin} is not in our Chennai pincode list.")
        rivals = list(db.scalars(select(Place).where(Place.kind == "pincode")))
        cells = _voronoi_cells(place, rivals, MAX_RADIUS_M["pincode"])
        return {"cells": cells, "name": f"PIN {place.name}", "input": pin}

    if selection_type == "locality":
        place = None
        if value and value.isdigit():
            place = db.get(Place, int(value))
        if not place:
            place = db.scalar(select(Place).where(Place.kind == "locality", func.lower(Place.name) == (value or "").lower().strip()))
        if not place:
            raise AreaError(f"Locality '{value}' not found. Pick one from the search suggestions.")
        rivals = [p for p in db.scalars(select(Place).where(Place.kind == "locality", Place.place_type.in_(LOCALITY_TYPES)))
                  if geo.haversine_m(p.lat, p.lng, place.lat, place.lng) < 6000]
        radius = MAX_RADIUS_M.get(place.place_type or "locality", 1500)
        cells = _voronoi_cells(place, rivals, radius)
        return {"cells": cells, "name": place.name, "input": place.name}

    raise AreaError(f"Unknown selection type {selection_type}")


def nearest_locality(db: Session, lat: float, lng: float, max_m: float = 4000) -> str | None:
    best = None
    d = 0.03
    for p in db.scalars(select(Place).where(Place.kind == "locality", Place.place_type.in_(LOCALITY_TYPES),
                                            Place.lat.between(lat - d, lat + d), Place.lng.between(lng - d, lng + d))):
        dist = geo.haversine_m(lat, lng, p.lat, p.lng)
        if dist <= max_m and (best is None or dist < best[0]):
            best = (dist, p.name)
    return best[1] if best else None


def search(db: Session, q: str, limit: int = 12) -> list[dict]:
    q = (q or "").strip()
    if not q:
        return []
    if q.isdigit():
        rows = db.scalars(select(Place).where(Place.kind == "pincode", Place.pincode.like(f"{q}%"))
                          .order_by(Place.pincode).limit(limit))
    else:
        rows = db.scalars(select(Place).where(or_(Place.name.ilike(f"{q}%"), Place.name.ilike(f"% {q}%")))
                          .order_by(Place.kind.desc(), func.length(Place.name)).limit(limit))
    return [{"id": p.id, "kind": p.kind, "name": p.name, "pincode": p.pincode, "place_type": p.place_type,
             "lat": p.lat, "lng": p.lng} for p in rows]
