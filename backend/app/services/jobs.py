"""Tiny persistent background-job runner.

Jobs live in the `jobs` table (so progress survives page reloads and is visible to every
user); execution happens on a small thread pool. On startup, jobs left `running` by a
crash/restart are re-queued. For production this maps 1:1 onto Celery/RQ/Arq — the
job table and step protocol stay the same.
"""
from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Job, utcnow

log = logging.getLogger("jobs")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="job")
HANDLERS: dict[str, Callable[["JobContext"], None]] = {}


def handler(kind: str, steps: list[tuple[str, str]], on_fail: Callable | None = None):
    """Register a job handler with its ordered (key, label) steps and an optional failure hook."""
    def deco(fn):
        fn.steps, fn.on_fail = steps, on_fail
        HANDLERS[kind] = fn
        return fn
    return deco


class StepFailed(RuntimeError):
    pass


class JobContext:
    """Passed to handlers. Each step is persisted so the UI can show a live checklist."""

    def __init__(self, db: Session, job: Job, steps: list[tuple[str, str]]):
        self.db, self.job = db, job
        if not job.steps:
            job.steps = [{"key": k, "label": lbl, "status": "pending", "detail": None} for k, lbl in steps]
            db.commit()

    def step(self, key: str, status: str, detail: str | None = None) -> None:
        steps = [dict(s) for s in self.job.steps]
        done = 0
        for s in steps:
            if s["key"] == key:
                s["status"], s["detail"] = status, detail
            if s["status"] in ("done", "skipped", "warning"):
                done += 1
        self.job.steps = steps
        self.job.progress = round(done / max(len(steps), 1), 2)
        self.db.commit()

    @property
    def ref_id(self) -> int:
        return self.job.ref_id


def enqueue(db: Session, kind: str, ref_id: int) -> Job:
    job = Job(kind=kind, ref_id=ref_id, status="queued", steps=[])
    db.add(job)
    db.commit()
    _pool.submit(_run, job.id)
    return job


def retry(db: Session, job: Job) -> Job:
    job.status, job.error, job.progress = "queued", None, 0
    job.steps = [{**s, "status": "pending", "detail": None} for s in (job.steps or [])]
    db.commit()
    _pool.submit(_run, job.id)
    return job


def _run(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job or job.status not in ("queued",):
            return
        fn = HANDLERS[job.kind]
        job.status, job.attempts = "running", job.attempts + 1
        db.commit()
        try:
            ctx = JobContext(db, job, fn.steps)
            fn(ctx)
            job.status, job.progress = "succeeded", 1.0
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            job = db.get(Job, job_id)
            log.error("job %s failed: %s", job_id, traceback.format_exc())
            steps = [dict(s) for s in job.steps or []]
            for s in steps:
                if s["status"] == "running":
                    s["status"], s["detail"] = "failed", str(exc)[:300]
            job.steps = steps
            job.status, job.error = "failed", str(exc)[:1000]
            db.commit()
            on_fail = getattr(fn, "on_fail", None)
            if on_fail:
                on_fail(db, job, exc)
    finally:
        db.close()


def resume_pending() -> None:
    db = SessionLocal()
    try:
        for job in db.scalars(select(Job).where(Job.status.in_(["queued", "running"]))):
            job.status = "queued"
            job.updated_at = utcnow()
            db.commit()
            _pool.submit(_run, job.id)
    finally:
        db.close()


def job_dict(job: Job | None) -> dict | None:
    if not job:
        return None
    return {"id": job.id, "kind": job.kind, "status": job.status, "progress": job.progress,
            "steps": job.steps, "error": job.error, "attempts": job.attempts,
            "updated_at": job.updated_at.isoformat() + "Z" if job.updated_at else None}
