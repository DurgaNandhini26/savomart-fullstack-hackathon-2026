"""Grounding check: every number the model writes must exist in the fact sheet.

We flatten the fact sheet into a set of allowed numeric values (plus common
roundings: 12,345 -> 12.3k / 12,000 / 12.3; 0.42 -> 42%), extract every number from
the generated text, and report any that can't be traced.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

NUM_RE = re.compile(r"(?<![\w.])(-?\d[\d,]*(?:\.\d+)?)(\s?(?:%|k|K|km|m|lakh|L|sq\s?ft)?)")
# small integers are used as ordinary words ("top 3 hotspots", "2 options") — allow them
TRIVIAL = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100}


def _flatten(obj, out: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _flatten(v, out)
    elif isinstance(obj, str):
        for m in NUM_RE.finditer(obj):
            try:
                out.append(float(m.group(1).replace(",", "")))
            except ValueError:
                pass


def allowed_values(facts: dict) -> list[float]:
    vals: list[float] = []
    _flatten(facts, vals)
    expanded = set()
    for v in vals:
        expanded.add(v)
        expanded.add(round(v))
        expanded.add(round(v, 1))
        if 0 < abs(v) <= 1:
            expanded.add(round(v * 100))            # share -> percent
            expanded.add(round(v * 100, 1))
        if abs(v) >= 1000:
            expanded.add(round(v / 1000, 1))        # 12,345 -> 12.3 (k)
            expanded.add(round(v / 1000))
            expanded.add(round(v, -2))
            expanded.add(round(v, -3))
            expanded.add(round(v / 100000, 1))      # lakh
            expanded.add(round(v / 100000, 2))
        if abs(v) >= 100:
            expanded.add(round(v, -1))
            expanded.add(round(v, -2))
    return sorted(expanded)


def numbers_in(text: str) -> list[tuple[str, float]]:
    out = []
    for m in NUM_RE.finditer(text):
        raw = m.group(1)
        try:
            out.append((m.group(0).strip(), float(raw.replace(",", ""))))
        except ValueError:
            continue
    return out


def check(texts: Iterable[str], facts: dict, rel_tol: float = 0.02) -> dict:
    allowed = allowed_values(facts)
    cited, untraced = 0, []
    for t in texts:
        for raw, v in numbers_in(t or ""):
            if abs(v) in TRIVIAL or 1900 <= v <= 2100:  # small counts / years
                continue
            cited += 1
            if not any(abs(v - a) <= max(rel_tol * abs(a), 0.051) for a in allowed):
                untraced.append(raw)
    return {"numbers_cited": cited, "untraced": untraced, "grounded": not untraced}


def texts_of(narrative: dict) -> list[str]:
    out: list[str] = []
    for v in narrative.values():
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            out.extend(x if isinstance(x, str) else " ".join(str(y) for y in x.values()) if isinstance(x, dict) else str(x)
                       for x in v)
    return out
