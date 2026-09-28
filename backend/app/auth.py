"""Deliberately simple auth: seeded demo users + HMAC-signed bearer tokens.

Real SSO is out of scope for the hackathon; what matters is that every endpoint
enforces *role-based access* on the server, not just in the UI.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

ROLES = ("bd_manager", "bd_exec", "survey_manager", "survey_exec")
TOKEN_TTL_S = 7 * 24 * 3600


def hash_password(pw: str, salt: str | None = None) -> str:
    salt = salt or base64.b64encode(hashlib.sha256(str(time.time_ns()).encode()).digest()[:12]).decode()
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000)
    return f"{salt}${base64.b64encode(dk).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(pw, salt), stored)


def _sign(payload: bytes) -> str:
    return hmac.new(get_settings().secret_key.encode(), payload, hashlib.sha256).hexdigest()


def make_token(user: User) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"uid": user.id, "exp": int(time.time()) + TOKEN_TTL_S}).encode())
    return f"{payload.decode()}.{_sign(payload)}"


def read_token(token: str) -> int | None:
    try:
        payload, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(_sign(payload.encode()), sig):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
        if data["exp"] < time.time():
            return None
        return int(data["uid"])
    except Exception:  # noqa: BLE001
        return None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("token", "")
    uid = read_token(token) if token else None
    user = db.get(User, uid) if uid else None
    if not user or not user.active:
        raise HTTPException(401, "Not signed in")
    return user


def require(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"This action needs role: {', '.join(roles)}")
        return user
    return dep


def user_dict(u: User | None) -> dict | None:
    if not u:
        return None
    return {"id": u.id, "username": u.username, "name": u.name, "role": u.role, "phone": u.phone}
