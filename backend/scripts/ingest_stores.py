"""Fetch Savomart's operational stores from the internal Stores API.

The raw response is kept in data/seed/stores.json so the app still works
(and demos) if the API is unreachable; the snapshot row records which one was used.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app import geo  # noqa: E402
from app.config import DATA_DIR, get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import DataSnapshot, Store  # noqa: E402

SEED = DATA_DIR / "seed" / "stores.json"


def fetch() -> tuple[list[dict], str]:
    s = get_settings()
    if s.stores_api_token:
        try:
            r = httpx.get(s.stores_api_url, headers={"X-cron-token": s.stores_api_token}, timeout=30)
            r.raise_for_status()
            payload = r.json()
            if payload.get("status") == "success":
                SEED.parent.mkdir(parents=True, exist_ok=True)
                SEED.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
                return payload["data"], "live API"
        except Exception as exc:  # noqa: BLE001
            print(f"   ! stores API failed ({exc!r}); using cached seed")
    else:
        print("   ! STORES_API_TOKEN not set; using cached seed")
    return json.loads(SEED.read_text(encoding="utf-8"))["data"], "cached seed (data/seed/stores.json)"


def ingest(db) -> int:
    print("-> Savomart stores")
    rows, origin = fetch()
    db.execute(delete(Store))
    n = 0
    for r in rows:
        g = r.get("geocoordinates") or {}
        lat, lng = g.get("latitude"), g.get("longitude")
        if lat is None or lng is None:
            continue
        db.add(Store(store_code=r["store_code"], name=r["name"], address=r.get("address"),
                     zone=r.get("zone"), lat=lat, lng=lng, h3_9=geo.cell(lat, lng, 9),
                     is_operational=bool(r.get("is_operational", True))))
        n += 1
    db.add(DataSnapshot(source="stores", record_count=n, notes=origin))
    db.commit()
    print(f"   {n} stores ({origin})")
    return n


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        ingest(s)
