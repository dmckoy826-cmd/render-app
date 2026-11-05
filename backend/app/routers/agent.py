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
from ..config import MEDIA_DIR
from ..db import get_db
from ..models import Job, ModelDoc, Render
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
        settings = job.settings or {}
        assignments = settings.get("_assignment_snapshot")
        if assignments is None:  # Compatibility with jobs queued before this change.
            assignments = runner.agent_assignment_snapshot(db, m.id)
            job.settings = {**settings, "_assignment_snapshot": assignments}
            db.commit()
        base["settings"] = {k: v for k, v in job.settings.items() if not k.startswith("_")}
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
    if job.status != "running":
        raise HTTPException(409, "job is not running")
    job.progress = max(0, min(100, int(body.get("progress", job.progress))))
    job.stage = str(body.get("stage", job.stage))[:200]
    db.commit()
    return job_out(job, db)


@router.post("/heartbeat")
def heartbeat(body: dict):
    agentstate.ping(str(body.get("name", "")))
    return {"ok": True}


def _valid_geometry(data: bytes, struct: dict) -> None:
    import math
    if len(data) > 100 * 1024 * 1024:
        raise HTTPException(413, "geometry preview is larger than 100 MB")
    try:
        geometry = json.loads(data)
        if not isinstance(geometry, dict) or geometry.get("version") != 1 or geometry.get("units") != "inches":
            raise ValueError("invalid geometry header")
        known = {p["id"] for p in struct.get("parts", [])}
        seen = set()
        for p in geometry.get("parts", []):
            key, positions = p["id"], p["positions"]
            triangles, lines = p["triangles"], p["lines"]
            if key not in known or key in seen or len(positions) % 3 or len(triangles) % 3 or len(lines) % 2:
                raise ValueError("invalid part identity or array lengths")
            seen.add(key)
            if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in positions):
                raise ValueError("non-finite vertex")
            if any(isinstance(x, bool) or not isinstance(x, int) or x < 0 or x >= len(positions) // 3
                   for x in triangles + lines):
                raise ValueError("geometry index out of range")
        if not isinstance(geometry.get("parts"), list):
            raise ValueError("missing geometry parts")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(400, f"invalid geometry preview: {exc}") from exc


def _image_size(data: bytes) -> tuple[int, int]:
    from io import BytesIO
    from PIL import Image
    try:
        with Image.open(BytesIO(data)) as img:
            if img.format != "PNG":
                raise ValueError("expected PNG")
            size = img.size
            img.verify()
        # Verify decompression as well as PNG container/chunk integrity.
        with Image.open(BytesIO(data)) as img:
            img.load()
        return size
    except Exception as exc:
        raise HTTPException(400, f"invalid PNG image: {exc}") from exc


@router.post("/jobs/{job_id}/complete")
async def complete(job_id: int,
                   structure: str = Form(None),
                   manifest: str = Form(None),
                   duration_s: float = Form(None),
                   geometry: UploadFile = None,
                   files: list[UploadFile] = [],
                   db: Session = Depends(get_db)):
    agentstate.ping()
    job = db.get(Job, job_id)
    if not job or job.status != "running":
        raise HTTPException(409, "job is not running")
    model = db.get(ModelDoc, job.model_id)
    if not model:
        raise HTTPException(404, "model not found")

    if job.kind == "analyze":
        try:
            struct = json.loads(structure) if structure else None
        except json.JSONDecodeError as exc:
            raise HTTPException(400, f"invalid structure JSON: {exc}") from exc
        if not isinstance(struct, dict) or not struct.get("parts"):
            raise HTTPException(400, "analyze jobs must return a nonempty structure JSON")
        # The URL is always generated by this server, never trusted from a worker.
        struct.pop("geometry_url", None)
        geom_data = None
        if struct.get("target_schema") == "rhino-geometry-v1":
            if geometry is None:
                raise HTTPException(400, "updated Rhino analysis must include its geometry preview")
            geom_data = await geometry.read(100 * 1024 * 1024 + 1)
            _valid_geometry(geom_data, struct)
        elif geometry is not None:
            raise HTTPException(400, "geometry provided without a supported target schema")
        preview_data = None
        if files:
            if len(files) != 1:
                raise HTTPException(400, "expected at most one analysis preview")
            preview_data = await files[0].read()
            _image_size(preview_data)
        analyze_preview = None
        if preview_data:
            analyze_preview = f"previews/{uuid.uuid4().hex}.png"
            (MEDIA_DIR / analyze_preview).write_bytes(preview_data)
        if geom_data is not None:
            geom_rel = f"geometry/{uuid.uuid4().hex}.json"
            (MEDIA_DIR / geom_rel).write_bytes(geom_data)
            struct["geometry_url"] = f"/media/{geom_rel}"
        runner.apply_analysis(db, model, struct, preview_rel=analyze_preview)
    else:
        try:
            meta = json.loads(manifest) if manifest else None
        except json.JSONDecodeError as exc:
            raise HTTPException(400, f"invalid render manifest: {exc}") from exc
        if not isinstance(meta, dict) or meta.get("protocol") != 1:
            raise HTTPException(400, "render requires a completed worker manifest")
        is_test = meta.get("engine") in ("stub-rhino", "dev-fake-worker") and meta.get("simulation") is True
        if meta.get("engine") != "V-Ray" and not is_test:
            raise HTTPException(400, "render manifest does not identify V-Ray")
        if len(files) != 1 or files[0].filename != "render.png" or meta.get("image") != "render.png":
            raise HTTPException(400, "render requires exactly one render.png, not swatches or a viewport capture")
        data = await files[0].read()
        size = _image_size(data)
        settings = job.settings or {}
        expected = (int(settings.get("width", 1920)), int(settings.get("height", 1080)))
        if size != expected or (meta.get("width"), meta.get("height")) != expected:
            raise HTTPException(400, f"render dimensions {size} do not match requested {expected}")
        rel = f"renders/{uuid.uuid4().hex}.png"
        (MEDIA_DIR / rel).write_bytes(data)
        snapshot = runner.snapshot_from_agent_assignments(settings.get("_assignment_snapshot", []))
        db.add(Render(job_id=job.id, model_id=model.id, image_path=rel,
                      width=size[0], height=size[1], camera=settings.get("camera", "iso"),
                      duration_s=duration_s or 0.0, finishes_snapshot=snapshot))
        job.settings = dict(settings, _engine=meta["engine"])
        if is_test:
            job.settings = dict(job.settings, _simulation=meta["engine"])
        db.commit()

    job.status = "done"
    job.progress = 100
    job.stage = "Complete (simulated test)" if job.kind == "render" and (job.settings or {}).get("_simulation") else "Complete"
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
    if job.status != "running":
        raise HTTPException(409, "job is not running")
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
