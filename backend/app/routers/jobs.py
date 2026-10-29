"""Job queue: render requests, status, cancel."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import runner
from ..db import get_db
from ..models import Job, ModelDoc
from ..schemas import RenderJobIn
from .models import job_out

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(status: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(Job)
    if status and status != "all":
        q = q.filter(Job.status == status)
    return [job_out(j, db) for j in q.order_by(Job.created_at.desc()).limit(limit).all()]


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return job_out(j, db)


@router.post("/render")
def create_render_job(body: RenderJobIn, db: Session = Depends(get_db)):
    m = db.get(ModelDoc, body.model_id)
    if not m:
        raise HTTPException(404, "model not found")
    if m.status != "ready" or not m.structure:
        raise HTTPException(409, "model is not analyzed yet — wait for the analyze job to finish")
    j = runner.create_job(db, "render", m.id, body.settings.model_dump())
    return job_out(j, db)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "job not found")
    if j.status not in ("queued", "running"):
        raise HTTPException(409, f"job is {j.status}")
    j.status = "canceled"
    j.stage = "Canceled"
    db.commit()
    return job_out(j, db)
