"""Unit tests for the pure logic that decisions rest on."""
import pytest

from app.llm import grounding
from app.services import scoring as S
from app.services.catchment import split_by_bearing


# ---------------------------------------------------------------- scoring

def test_network_score_prefers_the_sweet_spot():
    assert S.network_score(0.3) < 20            # cannibalises an existing store
    assert S.network_score(3.5) == 100          # new catchment inside the supply cluster
    assert S.network_score(3.5) > S.network_score(12) > S.network_score(30)
    assert S.network_score(None) == 50


def test_percentiles_and_bands():
    d = S.Distributions({"pop_density": [1000, 2000, 3000, 4000]})
    assert d.pct("pop_density", 500) == 0
    assert d.pct("pop_density", 5000) == 100
    assert 40 <= d.pct("pop_density", 2500) <= 60
    assert S.band(75) == "Strong fit" and S.band(60) == "Promising" and S.band(10) == "Weak fit"


def _metrics(**over):
    m = {"pop_density": 15000, "people_per_outlet": 3000, "supermarkets_per_10k": 0.5, "generators_per_km2": 20,
         "affluence_per_km2": 10, "apartment_share": 0.2, "nearest_store_km": 3.5, "road_density": 15,
         "major_road_density": 1.0}
    m.update(over)
    return m


def test_score_is_explainable_and_monotonic():
    dist = S.Distributions({k: list(range(0, 40000, 400)) for k in S.DIST_METRICS})
    base = S.score(_metrics(), dist)
    # overall score is exactly the weighted sum of pillars
    assert base["score"] == pytest.approx(sum(p["score"] * p["weight"] for p in base["pillars"].values()), abs=0.2)
    assert sum(p["weight"] for p in base["pillars"].values()) == pytest.approx(1.0)
    denser = S.score(_metrics(pop_density=30000), dist)
    assert denser["pillars"]["demand"]["score"] > base["pillars"]["demand"]["score"]
    saturated = S.score(_metrics(supermarkets_per_10k=30000), dist)  # more modern trade -> smaller gap
    assert saturated["pillars"]["gap"]["score"] < base["pillars"]["gap"]["score"]
    assert all("source" in i for i in base["indicators"])


# ---------------------------------------------------------------- AI grounding

FACTS = {"estimated_residents": 48213, "fit_score": 72.4, "apartment_share": 0.42, "nearest": {"distance_km": 3.88}}


def test_grounding_accepts_faithful_text_with_roundings():
    txt = ["About 48,213 residents (48.2k) live here; fit 72.4/100.", "42% apartments, 3.88 km to the nearest store."]
    g = grounding.check(txt, FACTS)
    assert g["grounded"], g
    assert g["numbers_cited"] >= 4


def test_grounding_flags_invented_numbers():
    g = grounding.check(["Footfall grew 17.5% last year and 91,000 people visit daily."], FACTS)
    assert not g["grounded"]
    assert "17.5%" in g["untraced"] and any("91,000" in u for u in g["untraced"])


def test_grounding_ignores_small_counts_and_years():
    assert grounding.check(["Top 3 hotspots, as of 2026."], FACTS)["grounded"]


# ---------------------------------------------------------------- fair splitting

def _ring(n=120):
    import math
    items = []
    for i in range(n):
        ang = 2 * math.pi * i / n
        items.append((i, 13.0 + 0.004 * math.cos(ang), 80.2 + 0.004 * math.sin(ang), 50 + (i % 7) * 20))
    return items


@pytest.mark.parametrize("k", [1, 2, 3, 5])
def test_split_is_a_partition_with_balanced_effort(k):
    items = _ring()
    groups = split_by_bearing(items, (13.0, 80.2), k)
    keys = [x for g in groups for x in g]
    assert sorted(keys) == [i[0] for i in items]          # every lane assigned exactly once
    assert len(groups) == k
    w = {i[0]: i[3] for i in items}
    loads = [sum(w[x] for x in g) for g in groups]
    assert max(loads) - min(loads) <= max(w.values()) * 1.5  # balanced to within ~one lane


def test_split_groups_are_contiguous_wedges():
    items = _ring()
    groups = split_by_bearing(items, (13.0, 80.2), 4)
    for g in groups:  # indices on the ring are consecutive (mod n) inside each group
        s = sorted(g)
        gaps = sum(1 for a, b in zip(s, s[1:]) if b - a != 1)
        assert gaps <= 1
