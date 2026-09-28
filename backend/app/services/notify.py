from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Notification, User


def notify(db: Session, users: Iterable[int | User], kind: str, title: str, body: str | None = None,
           link: str | None = None) -> None:
    for u in users:
        uid = u.id if isinstance(u, User) else u
        if uid:
            db.add(Notification(user_id=uid, kind=kind, title=title, body=body, link=link))


def role_users(db: Session, role: str) -> list[User]:
    return list(db.scalars(select(User).where(User.role == role, User.active.is_(True))))
