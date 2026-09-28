"""One command to get a working, demo-ready database.

    python -m scripts.bootstrap            # load committed public-data snapshot + demo users + demo scenario
    python -m scripts.bootstrap --live     # re-ingest everything from Overpass / Stores API / Nominatim
    python -m scripts.bootstrap --no-demo  # public data + users only (empty pipeline)
    python -m scripts.bootstrap --fresh    # delete the existing database first
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="fetch public data from live sources instead of the snapshot")
    ap.add_argument("--no-demo", action="store_true", help="skip the demo scenario")
    ap.add_argument("--fresh", action="store_true", help="delete the database first")
    args = ap.parse_args()

    from app.config import get_settings
    db_file = Path(get_settings().database_url.replace("sqlite:///", ""))
    if args.fresh and db_file.exists():
        for suffix in ("", "-wal", "-shm"):
            Path(str(db_file) + suffix).unlink(missing_ok=True)
        print(f"-> removed {db_file}")

    from app import models  # noqa: F401 — registers tables
    from app.db import Base, SessionLocal, engine
    Base.metadata.create_all(engine)

    from scripts import snapshot
    if args.live or not snapshot.SNAPSHOT.exists():
        print("== live ingestion (Overpass can be slow; raw responses are cached in data/raw) ==")
        from scripts import build_baseline, ingest_osm, ingest_pincodes, ingest_stores
        with SessionLocal() as db:
            ingest_stores.ingest(db)
            ingest_osm.ingest_pois(db)
            ingest_osm.ingest_places(db)
            ingest_osm.ingest_roads(db)
            ingest_pincodes.ingest(db)
        build_baseline.main()
    else:
        print("== loading public-data snapshot ==")
        snapshot.load()

    from scripts.seed_demo import seed_users
    with SessionLocal() as db:
        seed_users(db)

    if not args.no_demo:
        from sqlalchemy import func, select

        from app.models import Property
        with SessionLocal() as db:
            has_data = db.scalar(select(func.count()).select_from(Property))
        if has_data:
            print("-> demo scenario skipped (database already has properties; use --fresh to reset)")
        else:
            print("== demo scenario ==")
            from scripts.demo_scenario import run
            run()
    print("\nDone. Start the API with:  uvicorn app.main:app --reload   (from backend/)")


if __name__ == "__main__":
    main()
