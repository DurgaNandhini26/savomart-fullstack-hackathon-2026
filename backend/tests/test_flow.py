"""End-to-end API test of the M1 -> M2 -> M3 loop, including access control and reuse."""
import time
import uuid
from datetime import datetime, timezone

import h3

from tests.conftest import CENTER


def wait_for(fn, timeout=20):
    t = time.time()
    while time.time() - t < timeout:
        v = fn()
        if v:
            return v
        time.sleep(0.2)
    raise AssertionError("timed out")


def test_full_loop(client, auth):
    PM, EX, SM, SU, SU2 = auth("priya"), auth("arun"), auth("lakshmi"), auth("suresh"), auth("divya")

    # ---------- M1: area analysis (background job) ----------
    cells8 = list({h3.cell_to_parent(c, 8) for c in h3.grid_disk(h3.latlng_to_cell(*CENTER, 9), 3)})[:4]
    assert client.post("/api/reports", json={"selection_type": "cells", "cells": cells8}, headers=EX).status_code == 403
    r = client.post("/api/reports", json={"selection_type": "cells", "cells": cells8}, headers=PM)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    rep = wait_for(lambda: (x := client.get(f"/api/reports/{rid}", headers=PM).json())["status"] == "completed" and x)
    assert 0 <= rep["score"] <= 100 and rep["band"]
    assert rep["hotspots"], "should suggest where to scout"
    assert rep["narrative"]["meta"]["mode"] == "template"
    assert rep["data_versions"]["model"]["version"]
    assert {s["status"] for s in rep["job"]["steps"]} <= {"done", "warning"}

    # ---------- M1 -> M2: mission ----------
    h = rep["hotspots"][0]
    users = {u["username"]: u for u in client.get("/api/users", headers=PM).json()}
    m = client.post("/api/missions", headers=PM, json={"title": "Scout #1", "assignee_id": users["arun"]["id"],
                                                        "lat": h["lat"], "lng": h["lng"], "report_id": rid,
                                                        "hotspot_rank": 1}).json()
    assert [x["id"] for x in client.get("/api/missions", headers=EX).json()] == [m["id"]]

    # ---------- M2: onboarding with bad-input handling ----------
    body = {"client_uuid": str(uuid.uuid4()), "mission_id": m["id"], "title": "Shop on main road", "lat": CENTER[0],
            "lng": CENTER[1], "device_lat": CENTER[0] + 0.01, "device_lng": CENTER[1], "property_type": "shop",
            "carpet_area_sqft": 2500, "frontage_ft": 25, "floor": "ground", "rent_monthly": 2_500_000,
            "road_facing": "main_road", "lease_years": 9}
    assert client.post("/api/properties", headers=EX, json={**body, "lat": 28.6, "lng": 77.2}).status_code == 422  # Delhi pin
    r = client.post("/api/properties", headers=EX, json=body)
    assert r.status_code == 201, r.text
    p = r.json()["property"]
    warnings = " ".join(p["data_quality"])
    assert "from where the phone was" in warnings and "looks unusual" in warnings  # wrong pin + rent units
    assert client.post("/api/properties", headers=EX, json=body).json()["duplicate_submit"] is True  # idempotent retry
    dup = client.post("/api/properties", headers=EX, json={**body, "client_uuid": str(uuid.uuid4())})
    assert dup.status_code == 409 and dup.json()["detail"]["duplicates"][0]["id"] == p["id"]

    detail = wait_for(lambda: (d := client.get(f"/api/properties/{p['id']}", headers=PM).json())["evaluation"] and d)
    ev = detail["evaluation"]
    assert ev["recommendation"] in ("go", "consider", "no_go") and ev["insights"] and ev["risks"]
    assert any("above the locality benchmark" in x for x in ev["risks"])

    # ---------- pipeline state machine ----------
    pid = p["id"]
    assert client.post(f"/api/properties/{pid}/transition", headers=EX, json={"to": "shortlisted", "note": "x"}).status_code == 422
    assert client.post(f"/api/properties/{pid}/transition", headers=PM, json={"to": "rejected", "note": "no"}).status_code == 422
    r = client.post(f"/api/properties/{pid}/transition", headers=PM, json={"to": "info_requested", "note": "Rent looks annual?"})
    assert r.json()["stage"] == "info_requested"
    r = client.patch(f"/api/properties/{pid}", headers=EX, json={"fields": {"rent_monthly": 210000}, "note": "was annual"})
    assert r.status_code == 200
    d = client.get(f"/api/properties/{pid}", headers=PM).json()
    assert d["stage"] == "submitted"  # executive's update sends it back for review
    assert [e["action"] for e in d["events"]][:3] == ["stage_change", "details_updated", "stage_change"]

    # ---------- M3: catchment study ----------
    st = client.post("/api/studies", headers=PM, json={"target_type": "property", "property_id": pid, "radius_m": 600}).json()
    assert st["status"] == "requested"
    assert client.get(f"/api/properties/{pid}", headers=PM).json()["stage"] == "catchment_study"
    assert client.post(f"/api/studies/{st['id']}/plan", headers=PM, json={"units": 2}).status_code == 403
    sd = client.post(f"/api/studies/{st['id']}/plan", headers=SM, json={"units": 2}).json()
    assert len(sd["units"]) == 2
    lanes = sd["lanes"]["features"]
    assert len({f["id"] for f in lanes}) == len(lanes) and all(f["properties"]["work_unit_id"] for f in lanes)
    u1, u2 = sd["units"]
    client.post(f"/api/work-units/{u1['id']}/assign", headers=SM, json={"assignee_id": users["suresh"]["id"]})
    client.post(f"/api/work-units/{u2['id']}/assign", headers=SM, json={"assignee_id": users["divya"]["id"]})

    def capture(H, unit_id):
        wu = client.get(f"/api/work-units/{unit_id}", headers=H).json()
        obs = [{"client_uuid": str(uuid.uuid4()), "lane_id": f["id"], "captured_at": datetime.now(timezone.utc).isoformat(),
                "data": {"status": "done", "households": 30, "kiranas": 1, "sec": "B", "footfall": "high",
                         "competitor_brands": ["More"]}} for f in wu["lanes"]["features"]]
        return obs, client.post("/api/survey/observations", headers=H, json={"observations": obs}).json()

    # a surveyor can't write to someone else's lanes
    other = client.get(f"/api/work-units/{u2['id']}", headers=SM).json()["lanes"]["features"][0]["id"]
    res = client.post("/api/survey/observations", headers=SU, json={"observations": [
        {"client_uuid": str(uuid.uuid4()), "lane_id": other, "captured_at": datetime.now(timezone.utc).isoformat(), "data": {}}]}).json()
    assert res["results"][0]["status"] == "rejected"

    obs, res = capture(SU, u1["id"])
    assert {r["status"] for r in res["results"]} == {"accepted"} and not res["studies_completed"]
    again = client.post("/api/survey/observations", headers=SU, json={"observations": obs[:3]}).json()
    assert {r["status"] for r in again["results"]} == {"duplicate"}  # offline re-sync is harmless
    _, res = capture(SU2, u2["id"])
    assert res["studies_completed"] == [st["code"]]

    sd = client.get(f"/api/studies/{st['id']}", headers=PM).json()
    ins = sd["insights"]
    assert sd["status"] == "completed" and ins["coverage"] == 1.0 and ins["households_observed"] == 30 * len(lanes)
    assert ins["sec_mix"] == {"B": 1.0} and ins["competitor_brands"]["More"] == len(lanes)

    # property re-evaluated with ground truth (new version)
    d = wait_for(lambda: (x := client.get(f"/api/properties/{pid}", headers=PM).json())["evaluation"]["trigger"] == "catchment_study" and x)
    assert d["evaluation"]["catchment_study_id"] == st["id"]
    assert "ground-truthed" in d["evaluation"]["pillars"]["catchment"]["label"]

    # ---------- reuse ----------
    b2 = {**body, "client_uuid": str(uuid.uuid4()), "title": "Next door", "lat": CENTER[0] + 0.0015,
          "device_lat": None, "device_lng": None, "rent_monthly": 150000}
    p2 = client.post("/api/properties", headers=EX, json=b2).json()["property"]
    pv = client.post("/api/studies/preview", headers=PM, json={"target_type": "property", "property_id": p2["id"], "radius_m": 500}).json()
    assert pv["fully_reused"] and pv["coverage"] >= 0.8
    st2 = client.post("/api/studies", headers=PM, json={"target_type": "property", "property_id": p2["id"], "radius_m": 500}).json()
    assert st2["status"] == "reused" and st2["has_insights"] and st2["reused"][0]["study_id"] == st["id"]

    # notifications reached the right people
    titles = [n["title"] for n in client.get("/api/notifications", headers=PM).json()["items"]]
    assert any(st["code"] in t and "complete" in t for t in titles)


def test_auth_is_enforced(client, auth):
    assert client.get("/api/reports").status_code == 401
    assert client.get("/api/reports", headers={"authorization": "Bearer forged.token"}).status_code == 401
    assert client.get("/api/studies", headers=auth("arun")).status_code == 403
    assert client.get("/api/my/assignments", headers=auth("priya")).status_code == 403


def test_assistant_answers_from_data(client, auth):
    r = client.post("/api/assistant/ask", headers=auth("priya"), json={"question": "How good is Kolathur?"}).json()
    assert r["facts"]["areas"][0]["area"] == "Kolathur"
    assert "Kolathur" in r["answer"] and r["meta"]["mode"] == "template"
