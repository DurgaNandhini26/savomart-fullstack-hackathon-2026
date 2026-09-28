"""Export / import the processed public-data tables as one gzipped SQLite file.

Public Overpass servers are often overloaded, so the repo ships the processed snapshot
(data/seed/public_data.sqlite.gz, ~9 MB). `python -m scripts.bootstrap` loads it; the
ingestion scripts can rebuild it from live sources at any time (`--live`).
"""
from __future__ import annotations

import gzip
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR  # noqa: E402
from app import models  # noqa: E402,F401 — registers tables on Base.metadata
from app.db import Base, engine  # noqa: E402

SNAPSHOT = DATA_DIR / "seed" / "public_data.sqlite.gz"
TABLES = ["stores", "pois", "roads", "places", "cell_stats", "opportunity_cells", "baseline_meta", "data_snapshots"]


def _db_path() -> str:
    return engine.url.database


def export() -> Path:
    tmp = Path(tempfile.mkdtemp()) / "snap.sqlite"
    src = sqlite3.connect(_db_path())
    dst = sqlite3.connect(tmp)
    for t in TABLES:
        ddl = src.execute("select sql from sqlite_master where type='table' and name=?", (t,)).fetchone()[0]
        dst.execute(ddl)
        cols = [r[1] for r in src.execute(f"pragma table_info({t})")]
        rows = src.execute(f"select {','.join(cols)} from {t}").fetchall()
        dst.executemany(f"insert into {t} ({','.join(cols)}) values ({','.join('?' * len(cols))})", rows)
        print(f"   {t}: {len(rows):,}")
    dst.commit()
    dst.execute("vacuum")
    dst.close()
    src.close()
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "rb") as f, gzip.open(SNAPSHOT, "wb", compresslevel=9) as g:
        shutil.copyfileobj(f, g)
    print(f"-> wrote {SNAPSHOT} ({SNAPSHOT.stat().st_size / 1e6:.1f} MB)")
    return SNAPSHOT


def load() -> None:
    Base.metadata.create_all(engine)
    tmp = Path(tempfile.mkdtemp()) / "snap.sqlite"
    with gzip.open(SNAPSHOT, "rb") as g, open(tmp, "wb") as f:
        shutil.copyfileobj(g, f)
    con = sqlite3.connect(_db_path())
    con.execute("attach database ? as snap", (str(tmp),))
    for t in TABLES:
        cols = [r[1] for r in con.execute(f"pragma snap.table_info({t})")]
        mine = {r[1] for r in con.execute(f"pragma main.table_info({t})")}
        cols = [c for c in cols if c in mine]
        con.execute(f"delete from main.{t}")
        con.execute(f"insert into main.{t} ({','.join(cols)}) select {','.join(cols)} from snap.{t}")
        n = con.execute(f"select count(*) from main.{t}").fetchone()[0]
        print(f"   {t}: {n:,}")
    con.commit()
    con.execute("detach database snap")
    con.close()


if __name__ == "__main__":
    export() if (sys.argv[1:] or ["export"])[0] == "export" else load()
