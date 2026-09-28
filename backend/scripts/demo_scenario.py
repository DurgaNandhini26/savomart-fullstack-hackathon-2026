"""Seed a realistic demo scenario by *driving the real API as each persona*.

Nothing is inserted behind the API's back, so every evaluation, audit event and
notification is exactly what the product would produce. Survey observations are
synthetic (plausible, randomised) — clearly a demo stand-in for field data.
"""
from __future__ import annotations

import random
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

rnd = random.Random(7)


def photo_png(hue: int, variant: int, w: int = 480, h: int = 320) -> bytes:
    """A simple drawn storefront as PNG (pure Python — the demo has no real field photos)."""
    import colorsys
    import struct
    import zlib

    def rgb(hh, s, l):
        r, g, b = colorsys.hls_to_rgb((hh % 360) / 360, l, s)
        return bytes((int(r * 255), int(g * 255), int(b * 255)))

    sky, wall, sign, shutter, road, line = (rgb(hue + 180, .4, .85), rgb(hue, .2, .82), rgb(hue, .55, .42),
                                            rgb(220, .1, .35), rgb(220, .05, .6), rgb(220, .1, .45))
    rows = []
    for y in range(h):
        row = bytearray()
        for x in range(w):
            if y > h * 0.8:
                c = road if (y - int(h * 0.8)) % 14 else line
            elif w * 0.12 < x < w * 0.88 and h * 0.22 < y <= h * 0.8:
                if y < h * 0.34:
                    c = sign
                elif w * 0.18 < x < w * 0.82 and y > h * 0.42:
                    c = line if (x // 9 + variant) % 2 == 0 and x % 9 == 0 else shutter
                else:
                    c = wall
            else:
                c = sky
            row += c
        rows.append(b"\x00" + bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


PROPS = [
    # key, report, hotspot, exec, title, dlat, dlng, details
    ("kolathur_a", "Kolathur", 1, "arun", "Corner showroom, Paper Mills Road", 0.0004, 0.0002,
     dict(property_type="showroom", carpet_area_sqft=2800, frontage_ft=32, floor="ground", ceiling_height_ft=14,
          rent_monthly=165000, deposit_months=6, lease_years=9, parking_2w=12, parking_4w=2, road_facing="main_road",
          road_width_ft=60, visibility=5, power_kw=25, truck_access=True, owner_name="Mr. Rajendran",
          owner_phone="+91 98410 22001", notes="Vacant since June. Owner prefers a retail brand; open to 5% escalation.")),
    ("kolathur_b", "Kolathur", 1, "arun", "First-floor hall above bakery", -0.0021, 0.0013,
     dict(property_type="other", carpet_area_sqft=1900, frontage_ft=18, floor="first", rent_monthly=70000,
          deposit_months=10, lease_years=5, parking_2w=4, parking_4w=0, road_facing="secondary", visibility=2,
          power_kw=8, truck_access=False, owner_name="Mrs. Latha", owner_phone="+91 98410 22002")),
    ("kolathur_c", "Kolathur", 1, "karthik", "Ground-floor shop near Retteri junction", 0.0012, -0.0006,
     dict(property_type="shop", carpet_area_sqft=2300, frontage_ft=26, floor="ground", rent_monthly=120000,
          deposit_months=6, lease_years=9, parking_2w=8, parking_4w=1, road_facing="main_road", visibility=4,
          power_kw=18, truck_access=True, owner_name="Mr. Babu", owner_phone="+91 98410 22003")),
    ("tambaram_a", "Tambaram", 1, "karthik", "Ground floor on GST Road service lane", 0.0003, -0.0003,
     dict(property_type="shop", carpet_area_sqft=3200, frontage_ft=35, floor="ground", rent_monthly=210000,
          deposit_months=8, lease_years=10, parking_2w=15, parking_4w=3, road_facing="main_road", visibility=4,
          power_kw=30, truck_access=True, owner_name="Sri Balaji Estates", owner_phone="+91 98410 22004")),
    ("tambaram_b", "Tambaram", 2, "karthik", "Interior-street house conversion", 0.0011, 0.0009,
     dict(property_type="ground_floor_residential", carpet_area_sqft=1100, frontage_ft=14, floor="ground",
          rent_negotiable=True, road_facing="interior", visibility=2, parking_2w=3, parking_4w=0,
          owner_name="Mr. Senthil", owner_phone="+91 98410 22005")),
    ("porur_a", "Porur", 1, "arun", "Standalone building near Porur junction", 0.0002, 0.0004,
     dict(property_type="standalone_building", carpet_area_sqft=4500, frontage_ft=40, floor="ground+first",
          rent_monthly=280000, deposit_months=10, lease_years=12, parking_2w=20, parking_4w=6, road_facing="main_road",
          visibility=5, power_kw=45, truck_access=True, owner_name="Mr. Venkatesh", owner_phone="+91 98410 22006")),
    ("porur_b", "Porur", 2, "arun", "Shop in Ramapuram arcade", -0.0006, 0.0008,
     dict(property_type="shop", carpet_area_sqft=2200, frontage_ft=20, floor="ground", rent_monthly=95000,
          deposit_months=6, lease_years=6, parking_2w=10, parking_4w=0, road_facing="secondary", visibility=3,
          power_kw=15, truck_access=False, owner_name="Arcade management", owner_phone="+91 98410 22007")),
    ("velachery_a", "Velachery", 1, "karthik", "Showroom on 100 Feet Road", 0.0003, 0.0001,
     dict(property_type="showroom", carpet_area_sqft=3000, frontage_ft=30, floor="ground", rent_monthly=420000,
          deposit_months=12, lease_years=9, parking_2w=10, parking_4w=4, road_facing="main_road", visibility=5,
          power_kw=35, truck_access=True, owner_name="Prime Realty", owner_phone="+91 98410 22008")),
]


def lane_obs(lane: dict, profile: dict) -> dict:
    L = lane["properties"]["length_m"]
    hw = lane["properties"]["highway"]
    if rnd.random() < 0.04:
        return {"status": "inaccessible", "notes": "Gated / no entry"}
    main = hw in ("primary", "secondary", "trunk", "tertiary")
    hh = max(0, int(L / 100 * rnd.gauss(profile["hh_per_100m"] * (0.5 if main else 1.0), 4)))
    return {
        "status": "done", "households": hh,
        "housing_type": rnd.choices(["independent", "apartments", "mixed", "gated", "commercial"],
                                    weights=profile["housing"])[0] if not main else "commercial",
        "sec": rnd.choices("ABCD", weights=profile["sec"])[0],
        "occupancy": rnd.choices(["high", "medium", "low"], weights=[7, 2, 1])[0],
        "kiranas": int(rnd.random() < (0.9 if main else 0.35)) + int(main and rnd.random() < 0.5),
        "supermarkets": int(main and rnd.random() < 0.15),
        "competitor_brands": rnd.sample(profile["brands"], k=1) if main and rnd.random() < 0.25 else [],
        "footfall": rnd.choices(["low", "medium", "high"], weights=[1, 3, 3] if main else [4, 4, 1])[0],
        "access": "car" if main else rnd.choice(["car", "car", "two_wheeler"]),
        "notes": "",
    }


def run() -> None:
    with TestClient(app) as c:
        def H(u):
            r = c.post("/api/auth/login", json={"username": u, "password": "savo@123"})
            return {"authorization": f"Bearer {r.json()['token']}"}

        PM = H("priya")
        users = {u["username"]: u for u in c.get("/api/users", headers=PM).json()}

        def wait(path, headers, done):
            for _ in range(600):
                d = c.get(path, headers=headers).json()
                if done(d):
                    return d
                time.sleep(0.25)
            raise RuntimeError(f"timeout waiting for {path}")

        # ------------------------------------------------ M1 reports
        print("-> area reports")
        reports = {}
        for label, sel, val in [("Kolathur", "locality", "Kolathur"), ("Tambaram", "locality", "Tambaram"),
                                ("Porur", "locality", "Porur"), ("Velachery", "locality", "Velachery"),
                                ("Anna Nagar", "locality", "Anna Nagar")]:
            hits = [h for h in c.get(f"/api/geo/search?q={val}", headers=PM).json() if h["kind"] == "locality"]
            exact = [h for h in hits if h["name"].lower() == val.lower()] or hits  # search ranks suburbs first
            r = c.post("/api/reports", headers=PM, json={"selection_type": sel, "value": str(exact[0]["id"])})
            reports[label] = r.json()["id"]
        # a custom grid-cell area too
        top = c.get("/api/geo/opportunity/top?limit=3", headers=PM).json()
        import h3
        cells = list(h3.grid_disk(top[0]["h3"], 1))
        r = c.post("/api/reports", headers=PM, json={"selection_type": "cells", "cells": cells,
                                                     "name": f"{top[0]['locality']} pocket (opportunity map)"})
        reports["custom"] = r.json()["id"]
        for k, rid in reports.items():
            d = wait(f"/api/reports/{rid}", PM, lambda d: d["status"] in ("completed", "failed"))
            reports[k] = d
            print(f"   {d['name']}: {d['score']} {d['band']}")

        # ------------------------------------------------ missions
        print("-> missions")
        missions = {}
        for key, rep, rank, ex, *_ in PROPS:
            mk = (rep, rank)
            if mk in missions:
                continue
            h = next(x for x in reports[rep]["hotspots"] if x["rank"] == rank)
            m = c.post("/api/missions", headers=PM, json={
                "title": f"{rep} — hotspot #{rank} ({h['label']})", "assignee_id": users[ex]["id"], "lat": h["lat"],
                "lng": h["lng"], "report_id": reports[rep]["id"], "hotspot_rank": rank, "radius_m": 600,
                "due_date": (date.today() + timedelta(days=7)).isoformat(),
                "brief": "Ground-floor retail, 2,000–4,000 sq ft, main-road frontage preferred.\nWhy here: " + "; ".join(h["reasons"])})
            missions[mk] = m.json()
        h = next(x for x in reports["Anna Nagar"]["hotspots"] if x["rank"] == 1)
        c.post("/api/missions", headers=PM, json={"title": f"Anna Nagar — hotspot #1 ({h['label']})", "assignee_id": users["karthik"]["id"],
                                                  "lat": h["lat"], "lng": h["lng"], "report_id": reports["Anna Nagar"]["id"],
                                                  "hotspot_rank": 1, "brief": "; ".join(h["reasons"])})

        # ------------------------------------------------ properties
        print("-> properties")
        props = {}
        for i, (key, rep, rank, ex, title, dlat, dlng, details) in enumerate(PROPS):
            m = missions[(rep, rank)]
            body = {"client_uuid": str(uuid.uuid4()), "mission_id": m["id"], "title": title,
                    "lat": m["lat"] + dlat, "lng": m["lng"] + dlng, "gps_accuracy_m": rnd.choice([6, 9, 14, 22]),
                    "device_lat": m["lat"] + dlat + 0.00005, "device_lng": m["lng"] + dlng, **details,
                    "confirm_not_duplicate": True}
            r = c.post("/api/properties", headers=H(ex), json=body)
            assert r.status_code == 201, r.text
            p = r.json()["property"]
            for n in range(2):
                c.post(f"/api/properties/{p['id']}/photos", headers=H(ex), data={"caption": "Demo placeholder photo"},
                       files={"file": (f"p{n}.png", photo_png(i * 47 + n * 90, n), "image/png")})
            props[key] = p
        for p in props.values():
            wait(f"/api/properties/{p['id']}", PM, lambda d: d["evaluation"] is not None)

        def move(key, to, note, who="priya", reason=None):
            r = c.post(f"/api/properties/{props[key]['id']}/transition", headers=H(who), json={"to": to, "note": note, "reason": reason})
            assert r.status_code == 200, r.text

        print("-> pipeline decisions")
        move("kolathur_b", "rejected", "First floor with 8 kW power and a 5-year lease — not workable for grocery.", reason="size_unsuitable")
        move("tambaram_b", "info_requested", "Please get a rent quote and check whether a 20 ft frontage is possible.")
        move("tambaram_a", "shortlisted", "Strong frontage on GST Road service lane. Get title documents and a written quote.")
        move("porur_a", "shortlisted", "Big format but excellent junction visibility. Proceed.")
        move("porur_a", "site_visit", "Site visit with ops on Thursday; check loading bay access.")
        move("kolathur_a", "shortlisted", "Best candidate in Kolathur. Proceed with owner documents.")
        c.post(f"/api/properties/{props['velachery_a']['id']}/comments", headers=PM,
               json={"note": "Rent is ~2x benchmark. Will discuss with leadership before rejecting."})

        # ------------------------------------------------ M3 studies
        print("-> catchment studies")
        SM = H("lakshmi")
        st_a = c.post("/api/studies", headers=PM, json={"target_type": "property", "property_id": props["kolathur_a"]["id"],
                                                        "radius_m": 600, "priority": "high",
                                                        "notes": "Owner wants an answer in 2 weeks."}).json()
        sd = c.post(f"/api/studies/{st_a['id']}/plan", headers=SM, json={"units": 3}).json()
        for u, who in zip(sd["units"], ["suresh", "divya", "mani"]):
            c.post(f"/api/work-units/{u['id']}/assign", headers=SM, json={"assignee_id": users[who]["id"]})
        kolathur = {"hh_per_100m": 24, "housing": [5, 3, 3, 1, 1], "sec": [1, 4, 5, 2], "brands": ["More", "Reliance Smart", "Local supermarket"]}
        for u, who in zip(sd["units"], ["suresh", "divya", "mani"]):
            wu = c.get(f"/api/work-units/{u['id']}", headers=H(who)).json()
            obs = [{"client_uuid": str(uuid.uuid4()), "lane_id": f["id"],
                    "captured_at": (datetime.now(timezone.utc) - timedelta(hours=rnd.randint(2, 40))).isoformat(),
                    "data": lane_obs(f, kolathur)} for f in wu["lanes"]["features"]]
            c.post("/api/survey/observations", headers=H(who), json={"observations": obs})
        wait(f"/api/studies/{st_a['id']}", PM, lambda d: d["status"] == "completed")
        wait(f"/api/properties/{props['kolathur_a']['id']}", PM,
             lambda d: d["evaluation"] and d["evaluation"]["trigger"] == "catchment_study")
        move("kolathur_a", "negotiation", "Survey confirms dense housing and no supermarket inside the catchment. Negotiate rent down to ₹1.5L.")

        # reuse: a second Kolathur property inside the surveyed catchment
        st_c = c.post("/api/studies", headers=PM, json={"target_type": "property", "property_id": props["kolathur_c"]["id"],
                                                        "radius_m": 400}).json()
        print(f"   {st_c['code']}: {st_c['status']} (reuses {[r['code'] for r in st_c['reused']]})")

        # in progress: Porur, partially surveyed
        st_p = c.post("/api/studies", headers=PM, json={"target_type": "property", "property_id": props["porur_a"]["id"],
                                                        "radius_m": 500, "due_date": (date.today() + timedelta(days=5)).isoformat()}).json()
        sd = c.post(f"/api/studies/{st_p['id']}/plan", headers=SM, json={"units": 2}).json()
        c.post(f"/api/work-units/{sd['units'][0]['id']}/assign", headers=SM, json={"assignee_id": users["suresh"]["id"]})
        c.post(f"/api/work-units/{sd['units'][1]['id']}/assign", headers=SM, json={"assignee_id": users["divya"]["id"]})
        porur = {"hh_per_100m": 18, "housing": [3, 5, 2, 2, 1], "sec": [2, 5, 4, 1], "brands": ["Reliance Smart", "More", "DMart"]}
        wu = c.get(f"/api/work-units/{sd['units'][0]['id']}", headers=H("suresh")).json()
        feats = wu["lanes"]["features"]
        obs = [{"client_uuid": str(uuid.uuid4()), "lane_id": f["id"], "captured_at": datetime.now(timezone.utc).isoformat(),
                "data": lane_obs(f, porur)} for f in feats[: int(len(feats) * 0.45)]]
        c.post("/api/survey/observations", headers=H("suresh"), json={"observations": obs})

        # requested: an area study waiting for the survey manager
        c.post("/api/studies", headers=PM, json={"target_type": "area", "report_id": reports["Tambaram"]["id"], "priority": "normal",
                                                 "notes": "Validate the Tambaram report before we commit two executives there."})
        print("-> demo scenario ready")


if __name__ == "__main__":
    run()
