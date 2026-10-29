"""Job execution.

Two runners:
  * mock  - in-process simulated Rhino/V-Ray engine (threaded, with staged progress).
            Analyze jobs synthesize a model structure via mockdata.build_structure();
            render jobs compose a simulated render via imaging.render_scene().
  * agent - jobs stay queued until the Rhino worker agent (worker/agent.py) claims them
            through /api/agent/* endpoints and posts back real results.

Everything here writes through SQLAlchemy so both runners share the same lifecycle.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import automatch, config, imaging, mockdata
from .config import PREVIEW_DIR, RENDER_DIR
from .db import SessionLocal
from .models import Assignment, Finish, Job, ModelDoc, Render

ANALYZE_STAGES = [
    ("Reading file header", 8),
    ("Importing geometry (Rhino 8)", 26),
    ("Extracting layers", 46),
    ("Scanning block definitions (BlockEdit)", 64),
    ("Measuring extents & units", 80),
    ("Building structure preview", 94),
]
RENDER_STAGES = [
    ("Launching Rhino 8 (headless)", 7),
    ("Opening model geometry", 18),
    ("Applying V-Ray materials & texture scale", 38),
    ("BlockEdit: updating block definitions", 50),
    ("Setting camera & lighting", 60),
    ("V-Ray progressive render", 88),
    ("Post-processing output", 97),
]
QUALITY_SECONDS = {"draft": 4.0, "standard": 8.5, "high": 14.0}


class JobCanceled(Exception):
    pass


def utcnow():
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enqueue / lifecycle
# --------------------------------------------------------------------------- #

def create_job(db: Session, kind: str, model_id: int, settings: dict | None = None) -> Job:
    job = Job(kind=kind, model_id=model_id, status="queued", runner=config.RUNNER,
              settings=settings or {}, stage="Queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    if config.RUNNER == "mock":
        threading.Thread(target=_run_mock_job, args=(job.id,), daemon=True).start()
    return job


def _stage_sleep(db: Session, job: Job, stage: str, progress: int, seconds: float) -> None:
    job.stage = stage
    job.progress = progress
    db.commit()
    end = time.time() + seconds
    while time.time() < end:
        time.sleep(min(0.25, max(0.05, end - time.time())))
        db.refresh(job)
        if job.status == "canceled":
            raise JobCanceled()


def _run_mock_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job or job.status != "queued":
            return
        job.status = "running"
        job.started_at = utcnow()
        db.commit()
        try:
            if job.kind == "analyze":
                _mock_analyze(db, job)
            else:
                _mock_render(db, job)
            db.refresh(job)
            if job.status == "canceled":
                raise JobCanceled()
            job.status = "done"
            job.progress = 100
            job.stage = "Complete"
            job.finished_at = utcnow()
            db.commit()
        except JobCanceled:
            job.finished_at = utcnow()
            job.stage = "Canceled"
            db.commit()
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error = str(exc)
            job.stage = "Failed"
            job.finished_at = utcnow()
            db.commit()
            model = db.get(ModelDoc, job.model_id)
            if job.kind == "analyze" and model:
                model.status = "failed"
                db.commit()


# --------------------------------------------------------------------------- #
# Mock analyze
# --------------------------------------------------------------------------- #

def _mock_analyze(db: Session, job: Job) -> None:
    model = db.get(ModelDoc, job.model_id)
    if not model:
        raise RuntimeError("model missing")
    model.status = "analyzing"
    db.commit()
    per = 0.55
    for stage, prog in ANALYZE_STAGES:
        _stage_sleep(db, job, stage, prog, per)
    apply_analysis(db, model, mockdata.build_structure(model.name))


def apply_analysis(db: Session, model: ModelDoc, structure: dict) -> None:
    """Store analyzed structure + preview image (shared by mock runner and agent)."""
    model.structure = structure
    model.units = structure.get("units", "inches")
    prev_rel = f"previews/{model.id}_{uuid.uuid4().hex[:8]}.png"
    imaging.structure_preview(structure, str(PREVIEW_DIR.parent / prev_rel))
    model.preview_path = prev_rel
    model.status = "ready"
    db.commit()


# --------------------------------------------------------------------------- #
# Mock render
# --------------------------------------------------------------------------- #

def build_finish_lookup(db: Session, model: ModelDoc) -> tuple[dict, dict, list[dict]]:
    """Resolve assignments -> (finish_lookup for imaging, layer colors, snapshot)."""
    structure = model.structure or {"parts": [], "layers": []}
    layer_colors = {l["name"]: l.get("color", "#8d929a") for l in structure.get("layers", [])}
    assignments = db.query(Assignment).filter(Assignment.model_id == model.id).all()
    finish_lookup: dict[str, tuple] = {}
    by_finish: dict[int, dict] = {}
    for a in assignments:
        f = db.get(Finish, a.finish_id)
        if not f:
            continue
        if a.target_kind == "layer":
            tex = imaging.Image.open(str(config.MEDIA_DIR / f.storage_path)).convert("RGB")
            tex.thumbnail((1024, 1024))
            mult = a.scale_multiplier or 1.0
            finish_lookup[a.target_name] = (tex, f.swatch_width_in * mult, f.swatch_height_in * mult)
        snap = by_finish.setdefault(f.id, {
            "finish_id": f.id, "name": f.name, "category": f.category,
            "thumb": f"/media/{f.thumb_path}" if f.thumb_path else "", "targets": [],
        })
        snap["targets"].append(f"{a.target_kind}:{a.target_name}")
    # part/block overrides: part wins over layer (resolved here into the layer map keys
    # used by the mock renderer, which paints per layer)
    for a in assignments:
        if a.target_kind in ("part", "block"):
            f = db.get(Finish, a.finish_id)
            if not f:
                continue
            for p in structure.get("parts", []):
                hit = (a.target_kind == "part" and p["name"] == a.target_name) or \
                      (a.target_kind == "block" and p.get("block") == a.target_name)
                if hit:
                    tex = imaging.Image.open(str(config.MEDIA_DIR / f.storage_path)).convert("RGB")
                    tex.thumbnail((1024, 1024))
                    mult = a.scale_multiplier or 1.0
                    # give the part its own virtual layer so it can differ from its layer-mates
                    vlayer = f"__part_{p['id']}"
                    p["_vlayer"] = vlayer
                    finish_lookup[vlayer] = (tex, f.swatch_width_in * mult, f.swatch_height_in * mult)
                    layer_colors[vlayer] = layer_colors.get(p["layer"], "#8d929a")
    return finish_lookup, layer_colors, list(by_finish.values())


def _mock_render(db: Session, job: Job) -> None:
    model = db.get(ModelDoc, job.model_id)
    if not model or not model.structure:
        raise RuntimeError("model is not analyzed yet")
    settings = job.settings or {}
    quality = settings.get("quality", "standard")
    total = QUALITY_SECONDS.get(quality, 8.5)
    weights = [0.8, 1.0, 1.4, 0.8, 0.8, 4.5, 0.7]
    wsum = sum(weights)
    for (stage, prog), w in zip(RENDER_STAGES, weights):
        _stage_sleep(db, job, stage, prog, total * w / wsum)
    produce_render(db, job, model)


def produce_render(db: Session, job: Job, model: ModelDoc, with_stages: bool = False) -> Render:
    """Generate the simulated render image + Render row (also used by the seed)."""
    settings = job.settings or {}
    width = int(settings.get("width", 1920))
    height = int(settings.get("height", 1080))
    camera = settings.get("camera", "iso")
    finish_lookup, layer_colors, snapshot = build_finish_lookup(db, model)
    # honor per-part virtual layers produced by build_finish_lookup
    structure = model.structure
    parts = []
    for p in structure.get("parts", []):
        q = dict(p)
        if "_vlayer" in p:
            q["layer"] = p.pop("_vlayer")
        parts.append(q)
    scene_struct = dict(structure, parts=parts)
    img = imaging.render_scene(scene_struct, finish_lookup=finish_lookup,
                               layer_colors=layer_colors, size=(width, height),
                               camera=camera, textured=True,
                               watermark="SIMULATED RENDER · mock engine — connect the Rhino worker for V-Ray output")
    rel = f"renders/{uuid.uuid4().hex}.png"
    img.save(str(RENDER_DIR.parent / rel), "PNG")
    started = job.started_at or utcnow()
    if started.tzinfo is None:  # SQLite returns naive datetimes; treat as UTC
        started = started.replace(tzinfo=timezone.utc)
    duration = max(0.05, (utcnow() - started).total_seconds())
    render = Render(job_id=job.id, model_id=model.id, image_path=rel, width=width,
                    height=height, camera=camera, duration_s=round(duration, 2),
                    finishes_snapshot=snapshot)
    db.add(render)
    db.commit()
    db.refresh(render)
    return render


# --------------------------------------------------------------------------- #
# Shared output helpers (agent runner uses the same contract)
# --------------------------------------------------------------------------- #

def auto_assign_from_names(db: Session, model: ModelDoc, threshold: float = 0.45,
                           overwrite: bool = False) -> int:
    structure = model.structure or {}
    targets = [l["name"] for l in structure.get("layers", [])]
    targets += [b["name"] for b in structure.get("blocks", [])]
    finishes = db.query(Finish).all()
    existing = {(a.target_kind, a.target_name) for a in
                db.query(Assignment).filter(Assignment.model_id == model.id).all()}
    applied = 0
    for s in automatch.suggest(targets, finishes, min_score=threshold):
        kind = "block" if s["target_name"] in {b["name"] for b in structure.get("blocks", [])} else "layer"
        if not overwrite and (kind, s["target_name"]) in existing:
            continue
        upsert_assignment(db, model.id, kind, s["target_name"], s["finish"].id)
        applied += 1
    return applied


def upsert_assignment(db: Session, model_id: int, kind: str, name: str,
                      finish_id: int, scale_multiplier: float = 1.0) -> Assignment:
    a = db.query(Assignment).filter(
        Assignment.model_id == model_id,
        Assignment.target_kind == kind,
        Assignment.target_name == name).first()
    if a:
        a.finish_id = finish_id
        a.scale_multiplier = scale_multiplier
        a.updated_at = utcnow()
    else:
        a = Assignment(model_id=model_id, target_kind=kind, target_name=name,
                       finish_id=finish_id, scale_multiplier=scale_multiplier)
        db.add(a)
    db.commit()
    db.refresh(a)
    return a
