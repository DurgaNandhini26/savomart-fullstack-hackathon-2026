"""Resilient Overpass client: mirror rotation, retries, tiling and an on-disk cache.

Public Overpass instances are frequently overloaded (504 / "dispatcher timeout"),
so every raw response is cached under data/raw/overpass/ and a re-run only
fetches what is missing.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import DATA_DIR  # noqa: E402

MIRRORS = [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
UA = "SavoSiteScout/0.1 (hackathon data ingestion; contact via repo)"
CACHE = DATA_DIR / "raw" / "overpass"


def tiles(bbox: tuple[float, float, float, float], rows: int, cols: int):
    s, w, n, e = bbox
    dlat, dlng = (n - s) / rows, (e - w) / cols
    for r in range(rows):
        for c in range(cols):
            yield (round(s + r * dlat, 5), round(w + c * dlng, 5),
                   round(s + (r + 1) * dlat, 5), round(w + (c + 1) * dlng, 5))


def query(ql: str, *, name: str, timeout: int = 180, max_rounds: int = 6, fmt: str = "json"):
    """Run an Overpass QL query with caching. Returns parsed JSON (or raw text for csv)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(ql.encode()).hexdigest()[:12]
    path = CACHE / f"{name}_{key}.{ 'json' if fmt == 'json' else 'csv'}"
    if path.exists() and path.stat().st_size > 0:
        text = path.read_text(encoding="utf-8")
        return json.loads(text) if fmt == "json" else text

    last_err = None
    for rnd in range(max_rounds):
        for url in MIRRORS:
            try:
                r = httpx.post(url, data={"data": ql}, headers={"User-Agent": UA},
                               timeout=timeout + 30)
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}")
                if fmt == "json":
                    data = r.json()
                    remark = (data.get("remark") or "").lower()
                    if "error" in remark or "timed out" in remark:
                        raise RuntimeError(data["remark"][:200])
                    path.write_text(r.text, encoding="utf-8")
                    return data
                path.write_text(r.text, encoding="utf-8")
                return r.text
            except Exception as exc:  # noqa: BLE001 — network is flaky; try the next mirror
                last_err = f"{url} -> {exc!r}"
            print(f"   ! {name}: {last_err}", flush=True)
            time.sleep(2)
        time.sleep(min(60, 10 * (rnd + 1)))
    raise RuntimeError(f"Overpass query {name} failed after retries: {last_err}")


def osm_timestamp(data: dict) -> str | None:
    return (data.get("osm3s") or {}).get("timestamp_osm_base")
