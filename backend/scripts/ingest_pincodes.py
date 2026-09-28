"""Chennai pincodes: centroid per pincode, then approximate pincode areas.

Sources, in order of preference:
  1. OGD India "All India Pincode Directory" (post offices with lat/long) via api.data.gov.in
     (set DATA_GOV_IN_API_KEY; the public sample key is rate-limited).
  2. Nominatim structured postalcode search (1 req/s, cached in data/raw/pincodes_nominatim.json).

Pincode *boundaries*: the OGD all-India boundary GeoJSON is large; for a first version we
approximate each pincode's area as the H3 cells whose nearest pincode centroid is that
pincode (a discrete Voronoi partition). It's labelled "approximate" in the UI.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app import geo  # noqa: E402
from app.config import DATA_DIR, get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import DataSnapshot, Place  # noqa: E402

CACHE = DATA_DIR / "raw" / "pincodes_nominatim.json"
SEED = DATA_DIR / "seed" / "pincodes.json"
OGD_RESOURCE = "5c2f62fe-5afa-4119-a499-fec9d604d5bd"
OGD_SAMPLE_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"
CANDIDATES = [f"600{n:03d}" for n in range(1, 131)] + ["601201", "601204", "601301", "602001", "602024",
                                                       "602105", "603103", "603202", "603203", "603209",
                                                       "603210", "603211", "600131"]


def from_ogd() -> dict[str, dict]:
    key = os.environ.get("DATA_GOV_IN_API_KEY", OGD_SAMPLE_KEY)
    out: dict[str, list] = {}
    for district in ("CHENNAI", "TIRUVALLUR", "KANCHIPURAM", "CHENGALPATTU"):
        offset = 0
        while True:
            r = httpx.get(f"https://api.data.gov.in/resource/{OGD_RESOURCE}", timeout=60, params={
                "api-key": key, "format": "json", "limit": 500, "offset": offset,
                "filters[district]": district,
            })
            r.raise_for_status()
            recs = r.json().get("records", [])
            for rec in recs:
                try:
                    lat, lng = float(rec["latitude"]), float(rec["longitude"])
                except (KeyError, TypeError, ValueError):
                    continue
                if geo.in_chennai(lat, lng):
                    out.setdefault(str(rec["pincode"]), []).append((lat, lng, rec.get("officename", "")))
            if len(recs) < 500:
                break
            offset += 500
    return {
        pin: {"lat": sum(p[0] for p in pts) / len(pts), "lng": sum(p[1] for p in pts) / len(pts),
              "name": pts[0][2], "source": "OGD pincode directory"}
        for pin, pts in out.items()
    }


def from_nominatim() -> dict[str, dict]:
    s = get_settings()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    for pin in CANDIDATES:
        if pin in cache:
            continue
        try:
            r = httpx.get(f"{s.nominatim_url}/search", timeout=30, headers={"User-Agent": s.nominatim_user_agent},
                          params={"postalcode": pin, "country": "India", "format": "json", "limit": 1,
                                  "addressdetails": 1})
            r.raise_for_status()
            res = r.json()
            cache[pin] = res[0] if res else None
        except Exception as exc:  # noqa: BLE001
            print(f"   ! {pin}: {exc!r}")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache), encoding="utf-8")
        time.sleep(1.1)  # Nominatim usage policy: max 1 request / second
    out = {}
    for pin, hit in cache.items():
        if not hit:
            continue
        lat, lng = float(hit["lat"]), float(hit["lon"])
        if not geo.in_chennai(lat, lng):
            continue
        addr = hit.get("address") or {}
        name = addr.get("suburb") or addr.get("neighbourhood") or addr.get("city_district") or \
            addr.get("town") or addr.get("village") or hit.get("display_name", "").split(",")[0]
        name = re.sub(r"^Zone \d+\s+", "", name or "")  # "Zone 8 Anna Nagar" -> "Anna Nagar"
        out[pin] = {"lat": lat, "lng": lng, "name": name, "source": "Nominatim postcode centroid"}
    return out


def ingest(db) -> int:
    print("-> pincodes")
    pins: dict[str, dict] = {}
    if SEED.exists():
        pins = json.loads(SEED.read_text(encoding="utf-8"))
        print(f"   using committed seed ({len(pins)} pincodes)")
    else:
        try:
            pins = from_ogd()
            print(f"   OGD: {len(pins)} pincodes")
        except Exception as exc:  # noqa: BLE001
            print(f"   ! OGD API unavailable ({exc!r}); falling back to Nominatim")
        if len(pins) < 40:
            pins = {**from_nominatim(), **pins}
        SEED.parent.mkdir(parents=True, exist_ok=True)
        SEED.write_text(json.dumps(pins, indent=1, ensure_ascii=False), encoding="utf-8")
    db.execute(delete(Place).where(Place.kind == "pincode"))
    for pin, p in sorted(pins.items()):
        db.add(Place(kind="pincode", name=f"{pin} {p.get('name') or ''}".strip(), pincode=pin,
                     lat=p["lat"], lng=p["lng"], source=p["source"]))
    db.add(DataSnapshot(source="pincodes", record_count=len(pins),
                        notes=", ".join(sorted({p['source'] for p in pins.values()}))))
    db.commit()
    print(f"   {len(pins)} pincodes stored")
    return len(pins)


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        ingest(s)
