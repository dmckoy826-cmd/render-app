"""Agent endpoints — the contract the real Rhino/V-Ray worker speaks.

The worker agent (worker/agent.py, runs on the Windows machine with Rhino 8 + V-Ray)
polls GET /api/agent/jobs/next, executes the job headlessly in Rhino, and reports back:

  POST /api/agent/jobs/{id}/progress  {progress, stage}
  POST /api/agent/jobs/{id}/complete  (multipart: structure JSON for analyze jobs,
                                       one or more PNG/JPG result images for render jobs)
  POST /api/agent/jobs/{id}/fail      {error}

Jobs are handled by the agent when the server runs with RENDER_RUNNER=agent.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import agentstate, runner
from ..config import MEDIA_DIR, PREVIEW_DIR, RENDER_DIR
from ..db import get_db
from ..models import Assignment, Finish, Job, ModelDoc, Render
from .finishes import finish_out
from .models import job_out

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _claim_next(db: Session) -> Job | None:
    job = (db.query(Job)
           .filter(Job.status == "queued", Job.runner == "agent")
           .order_by(Job.created_at.asc())
           .first())
    if job:
        job.status = "running"
        job.started_at = runner.utcnow()
        job.stage = "Claimed by Rhino agent"
        db.commit()
        db.refresh(job)
    return job


def _payload(db: Session, job: Job) -> dict:
    m = db.get(ModelDoc, job.model_id)
    base = {
        "job": job_out(job, db),
        "model": {
            "id": m.id, "name": m.name, "original_name": m.original_name,
            "file_url": f"/media/{m.storage_path}" if m.storage_path else None,
            "structure": m.structure,
        },
    }
    if job.kind == "render":
        assignments = []
        for a in db.query(Assignment).filter(Assignment.model_id == m.id).all():
            f = db.get(Finish, a.finish_id)
            if not f:
                continue
            assignments.append({
                "target_kind": a.target_kind,
                "target_name": a.target_name,
                "scale_multiplier": a.scale_multiplier,
                "finish": {**finish_out(f),
                           "file_url": f"/media/{f.storage_path}"},
            })
        base["settings"] = job.settings or {}
        base["assignments"] = assignments
    return base


@router.get("/jobs/next")
def next_job(name: str = "", db: Session = Depends(get_db)):
    agentstate.ping(name)
    job = _claim_next(db)
    if not job:
        return {"job": None}
    return _payload(db, job)


@router.post("/jobs/{job_id}/progress")
def progress(job_id: int, body: dict, db: Session = Depends(get_db)):
    agentstate.ping()
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    job.progress = max(0, min(100, int(body.get("progress", job.progress))))
    job.stage = str(body.get("stage", job.stage))[:200]
    db.commit()
    return job_out(job, db)


@router.post("/jobs/{job_id}/complete")
async def complete(job_id: int,
                   structure: str = Form(None),
                   duration_s: float = Form(None),
                   files: list[UploadFile] = [],
                   db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or job.status != "running":
        raise HTTPException(409, "job is not running")
    model = db.get(ModelDoc, job.model_id)

    saved: list[str] = []
    analyze_preview: str | None = None
    for f in files:
        data = await f.read()
        if not data:
            continue
        stem = f"{uuid.uuid4().hex[:12]}_{(f.filename or 'out.png')}"
        if job.kind == "analyze":
            rel = f"previews/{stem}"
            (MEDIA_DIR / rel).write_bytes(data)
            analyze_preview = rel  # real Rhino viewport capture — keep it
        else:
            rel = f"renders/{stem}"
            (MEDIA_DIR / rel).write_bytes(data)
        saved.append(rel)

    if job.kind == "analyze":
        try:
            struct = json.loads(structure) if structure else None
        except json.JSONDecodeError as exc:
            raise HTTPException(400, f"invalid structure JSON: {exc}")
        if not struct:
            raise HTTPException(400, "analyze jobs must return a structure JSON")
        runner.apply_analysis(db, model, struct, preview_rel=analyze_preview)
    else:
        _, _, snapshot = runner.build_finish_lookup(db, model)
        settings = job.settings or {}
        for i, rel in enumerate(saved):
            db.add(Render(job_id=job.id, model_id=model.id, image_path=rel,
                          width=int(settings.get("width", 0)) or 0,
                          height=int(settings.get("height", 0)) or 0,
                          camera=settings.get("camera", "iso"),
                          duration_s=duration_s or 0.0,
                          finishes_snapshot=snapshot))
        db.commit()

    job.status = "done"
    job.progress = 100
    job.stage = "Complete"
    job.finished_at = runner.utcnow()
    db.commit()
    db.refresh(job)
    return job_out(job, db)


@router.post("/jobs/{job_id}/fail")
def fail(job_id: int, body: dict, db: Session = Depends(get_db)):
    agentstate.ping()
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    job.status = "failed"
    job.error = str(body.get("error", ""))[:4000]
    job.stage = "Failed"
    job.finished_at = runner.utcnow()
    db.commit()
    if job.kind == "analyze":
        m = db.get(ModelDoc, job.model_id)
        if m:
            m.status = "failed"
            db.commit()
    return job_out(job, db)
