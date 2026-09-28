"""Seed demo users (one or more per persona). Password for everyone: savo@123"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import User  # noqa: E402

DEMO_PASSWORD = "savo@123"
USERS = [
    ("priya", "Priya Raman", "bd_manager", "+91 98400 11001"),
    ("arun", "Arun Kumar", "bd_exec", "+91 98400 11002"),
    ("karthik", "Karthik S", "bd_exec", "+91 98400 11003"),
    ("lakshmi", "Lakshmi Narayanan", "survey_manager", "+91 98400 11004"),
    ("suresh", "Suresh M", "survey_exec", "+91 98400 11005"),
    ("divya", "Divya R", "survey_exec", "+91 98400 11006"),
    ("mani", "Mani V", "survey_exec", "+91 98400 11007"),
]


def seed_users(db) -> None:
    for username, name, role, phone in USERS:
        if not db.scalar(select(User).where(User.username == username)):
            db.add(User(username=username, name=name, role=role, phone=phone,
                        password_hash=hash_password(DEMO_PASSWORD)))
    db.commit()
    print(f"-> {len(USERS)} demo users (password: {DEMO_PASSWORD})")


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        seed_users(s)
