"""Test fixtures: an isolated SQLite DB with a small synthetic "city" around Kolathur.

The synthetic data is deterministic, so API tests don't depend on Overpass or the
ingested OSM snapshot.
"""
import os
import random
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="sitescout-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(Path(_tmp, "uploads"))
os.environ["LLM_PROVIDER"] = "none"
os.environ["ENABLE_REVERSE_GEOCODE"] = "false"
os.environ["STORES_API_TOKEN"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import h3  # noqa: E402

from app import geo  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import BaselineMeta, CellStat, Place, Poi, Road, Store, User  # noqa: E402
from app.services import features as F  # noqa: E402
from app.services import scoring as S  # noqa: E402

CENTER = (13.1234, 80.2173)
USERS = [("priya", "bd_manager"), ("arun", "bd_exec"), ("karthik", "bd_exec"), ("lakshmi", "survey_manager"),
         ("suresh", "survey_exec"), ("divya", "survey_exec")]


def build_city(db) -> None:
    rnd = random.Random(42)
    origin = h3.latlng_to_cell(*CENTER, 9)
    cells = list(h3.grid_disk(origin, 8))
    for u, role in USERS:
        db.add(User(username=u, name=u.title(), role=role, password_hash=hash_password("savo@123")))
    db.add(Store(store_code="TST01", name="Test Store", zone="CHN", lat=13.13737, lng=80.20133,
                 h3_9=geo.cell(13.13737, 80.20133, 9)))
    db.add(Place(kind="locality", name="Kolathur", place_type="suburb", lat=CENTER[0], lng=CENTER[1], source="test"))
    db.add(Place(kind="pincode", name="600099 Kolathur", pincode="600099", lat=CENTER[0], lng=CENTER[1], source="test"))
    rid = 0
    for c in cells:
        lat, lng = h3.cell_to_latlng(c)
        pop = rnd.uniform(500, 3000)
        pois = {"grocery": rnd.randint(0, 3), "supermarket": rnd.randint(0, 1), "school": rnd.randint(0, 2),
                "bank": rnd.randint(0, 2), "food": rnd.randint(0, 4), "transit": rnd.randint(0, 2)}
        db.add(CellStat(h3_9=c, h3_8=h3.cell_to_parent(c, 8), lat=lat, lng=lng, buildings=200, res_buildings=150,
                        apartments=20, road_m=2000, res_road_m=1500, major_road_m=rnd.choice([0, 0, 300]),
                        est_population=pop, est_households=pop / 4, poi_counts=pois))
        for cat, n in pois.items():
            for i in range(n):
                plat, plng = lat + rnd.uniform(-0.001, 0.001), lng + rnd.uniform(-0.001, 0.001)
                db.add(Poi(osm_ref=f"n{c}{cat}{i}", category=cat, tag=f"shop={cat}", name=f"{cat} {i}",
                           lat=plat, lng=plng, h3_9=geo.cell(plat, plng, 9), h3_8=geo.cell(plat, plng, 8)))
        for k in range(4):  # 4 little streets per cell
            rid += 1
            a = [lng - 0.0012 + k * 0.0006, lat - 0.001]
            b = [lng - 0.0012 + k * 0.0006, lat + 0.001]
            db.add(Road(osm_id=rid, seg=0, name=f"Street {rid}", highway="residential", length_m=220, coords=[a, b],
                        mid_lat=lat, mid_lng=a[0], h3_9=c, h3_8=h3.cell_to_parent(c, 8)))
    db.flush()
    stores = F.chennai_stores(db)
    dists: dict[str, list] = {k: [] for k in S.DIST_METRICS}
    by8 = {h3.cell_to_parent(c, 8) for c in cells}
    for c8 in by8:
        m = F.derive(F.aggregate(db, h3.cell_to_children(c8, 9)), *h3.cell_to_latlng(c8), stores)
        for k in dists:
            dists[k].append(m[k])
    db.add(BaselineMeta(key="distributions", value=dists))
    db.commit()


@pytest.fixture(scope="session")
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        build_city(db)
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    def headers(username: str) -> dict:
        r = client.post("/api/auth/login", json={"username": username, "password": "savo@123"})
        assert r.status_code == 200, r.text
        return {"authorization": f"Bearer {r.json()['token']}"}
    return headers
