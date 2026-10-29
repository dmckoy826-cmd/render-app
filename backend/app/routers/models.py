"""Models: upload CAD files, inspect analyzed structure, map finishes, auto-match."""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import automatch, runner
from ..config import MEDIA_DIR, MODEL_DIR
from ..db import get_db
from ..models import Assignment, Finish, Job, ModelDoc, Preset, Render
from ..schemas import AssignmentIn, AutoMatchApplyIn, PresetApplyIn
from .finishes import finish_out

router = APIRouter(prefix="/api/models", tags=["models"])

MODEL_EXT = {".dwg", ".dxf", ".3dm", ".skp", ".obj", ".fbx", ".step", ".stp",
             ".iges", ".igs", ".sat", ".stl", ".3ds", ".ifc"}


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[-90:]


def model_out(m: ModelDoc) -> dict:
    s = m.structure or {}
    return {
        "id": m.id,
        "name": m.name,
        "original_name": m.original_name,
        "status": m.status,
        "units": m.units,
        "size_bytes": m.size_bytes,
        "preview_url": f"/media/{m.preview_path}" if m.preview_path else None,
        "layer_count": len(s.get("layers", [])),
        "block_count": len(s.get("blocks", [])),
        "part_count": len(s.get("parts", [])),
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def assignment_out(a: Assignment, db: Session) -> dict:
    f = db.get(Finish, a.finish_id)
    return {
        "id": a.id,
        "target_kind": a.target_kind,
        "target_name": a.target_name,
        "finish_id": a.finish_id,
        "scale_multiplier": a.scale_multiplier,
        "finish": finish_out(f) if f else None,
    }


def job_out(j: Job, db: Session) -> dict:
    m = db.get(ModelDoc, j.model_id)
    return {
        "id": j.id, "kind": j.kind, "model_id": j.model_id,
        "model_name": m.name if m else "?", "status": j.status,
        "progress": j.progress, "stage": j.stage, "runner": j.runner,
        "settings": j.settings, "error": j.error,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }


@router.post("")
async def upload_model(file: UploadFile, name: str = Form(None), db: Session = Depends(get_db)):
    orig = file.filename or "model.dwg"
    ext = ("." + orig.rsplit(".", 1)[-1].lower()) if "." in orig else ""
    if ext not in MODEL_EXT:
        raise HTTPException(400, f"unsupported file type '{ext}'. Accepted: {', '.join(sorted(MODEL_EXT))}")
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    stem = f"{uuid.uuid4().hex[:10]}_{_safe_name(orig)}"
    rel = f"models/{stem}"
    (MEDIA_DIR / rel).write_bytes(data)

    display = (name or "").strip() or re.sub(r"\.[^.]+$", "", orig)
    m = ModelDoc(name=display, original_name=orig, storage_path=rel,
                 content_type=file.content_type or "application/octet-stream",
                 size_bytes=len(data), status="uploaded")
    db.add(m)
    db.commit()
    db.refresh(m)
    job = runner.create_job(db, "analyze", m.id)
    return {"model": model_out(m), "job": job_out(job, db)}


@router.get("")
def list_models(db: Session = Depends(get_db)):
    return [model_out(m) for m in db.query(ModelDoc).order_by(ModelDoc.created_at.desc()).all()]


@router.get("/{model_id}")
def get_model(model_id: int, db: Session = Depends(get_db)):
    m = db.get(ModelDoc, model_id)
    if not m:
        raise HTTPException(404, "model not found")
    assignments = [assignment_out(a, db) for a in
                   db.query(Assignment).filter(Assignment.model_id == m.id).all()]
    jobs = [job_out(j, db) for j in db.query(Job).filter(Job.model_id == m.id)
            .order_by(Job.created_at.desc()).limit(8).all()]
    out = model_out(m)
    out["structure"] = m.structure
    out["assignments"] = assignments
    out["jobs"] = jobs
    return out


@router.delete("/{model_id}")
def delete_model(model_id: int, db: Session = Depends(get_db)):
    m = db.get(ModelDoc, model_id)
    if not m:
        raise HTTPException(404, "model not found")
    for r in db.query(Render).filter(Render.model_id == m.id).all():
        try:
            (MEDIA_DIR / r.image_path).unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(r)
    db.query(Assignment).filter(Assignment.model_id == m.id).delete()
    db.query(Job).filter(Job.model_id == m.id).delete()
    try:
        (MEDIA_DIR / m.storage_path).unlink(missing_ok=True)
        if m.preview_path:
            (MEDIA_DIR / m.preview_path).unlink(missing_ok=True)
    except OSError:
        pass
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.post("/{model_id}/reanalyze")
def reanalyze(model_id: int, db: Session = Depends(get_db)):
    m = db.get(ModelDoc, model_id)
    if not m:
        raise HTTPException(404, "model not found")
    m.status = "uploaded"
    db.commit()
    job = runner.create_job(db, "analyze", m.id)
    return job_out(job, db)


# --------------------------------------------------------------------------- #
# Assignments & auto-match
# --------------------------------------------------------------------------- #

@router.get("/{model_id}/assignments")
def list_assignments(model_id: int, db: Session = Depends(get_db)):
    rows = db.query(Assignment).filter(Assignment.model_id == model_id).all()
    return [assignment_out(a, db) for a in rows]


@router.post("/{model_id}/assignments")
def set_assignment(model_id: int, body: AssignmentIn, db: Session = Depends(get_db)):
    m = db.get(ModelDoc, model_id)
    if not m:
        raise HTTPException(404, "model not found")
    if body.finish_id is None:
        db.query(Assignment).filter(
            Assignment.model_id == model_id,
            Assignment.target_kind == body.target_kind,
            Assignment.target_name == body.target_name).delete()
        db.commit()
    else:
        if not db.get(Finish, body.finish_id):
            raise HTTPException(404, "finish not found")
        runner.upsert_assignment(db, model_id, body.target_kind, body.target_name,
                                 body.finish_id, body.scale_multiplier)
    rows = db.query(Assignment).filter(Assignment.model_id == model_id).all()
    return [assignment_out(a, db) for a in rows]


def _targets(m: ModelDoc) -> list[tuple[str, str]]:
    s = m.structure or {}
    out = [("layer", l["name"]) for l in s.get("layers", [])]
    out += [("block", b["name"]) for b in s.get("blocks", [])]
    return out


@router.get("/{model_id}/automatch")
def automatch_suggest(model_id: int, min_score: float = 0.35, db: Session = Depends(get_db)):
    m = db.get(ModelDoc, model_id)
    if not m or not m.structure:
        raise HTTPException(404, "model not analyzed yet")
    finishes = db.query(Finish).all()
    kinds = dict(_targets(m))
    out = []
    for s in automatch.suggest([n for _, n in _targets(m)], finishes, min_score=min_score):
        out.append({
            "target_kind": kinds.get(s["target_name"], "layer"),
            "target_name": s["target_name"],
            "finish_id": s["finish"].id,
            "finish": finish_out(s["finish"]),
            "score": s["score"],
        })
    return out


@router.post("/{model_id}/automatch/apply")
def automatch_apply(model_id: int, body: AutoMatchApplyIn, db: Session = Depends(get_db)):
    m = db.get(ModelDoc, model_id)
    if not m or not m.structure:
        raise HTTPException(404, "model not analyzed yet")
    suggestions = automatch_suggest(model_id, min_score=body.threshold, db=db)
    existing = {(a.target_kind, a.target_name) for a in
                db.query(Assignment).filter(Assignment.model_id == model_id).all()}
    applied = []
    for s in suggestions:
        key = (s["target_kind"], s["target_name"])
        if key in existing and not body.overwrite:
            continue
        runner.upsert_assignment(db, model_id, s["target_kind"], s["target_name"], s["finish_id"])
        applied.append(s)
    rows = db.query(Assignment).filter(Assignment.model_id == model_id).all()
    return {"applied": len(applied), "suggestions": applied,
            "assignments": [assignment_out(a, db) for a in rows]}


@router.post("/{model_id}/presets/{preset_id}/apply")
def apply_preset(model_id: int, preset_id: int, body: PresetApplyIn,
                 db: Session = Depends(get_db)):
    m = db.get(ModelDoc, model_id)
    preset = db.get(Preset, preset_id)
    if not m or not m.structure:
        raise HTTPException(404, "model not analyzed yet")
    if not preset:
        raise HTTPException(404, "preset not found")
    matches = []
    for kind, name in _targets(m):
        for rule in preset.rules or []:
            if rule.get("target_kind", "layer") != kind:
                continue
            pattern = rule.get("pattern", "")
            mode = rule.get("match", "contains")
            hit = False
            try:
                if mode == "exact":
                    hit = name.upper() == pattern.upper()
                elif mode == "starts_with":
                    hit = name.upper().startswith(pattern.upper())
                elif mode == "regex":
                    hit = re.search(pattern, name, re.IGNORECASE) is not None
                else:
                    hit = pattern.upper() in name.upper()
            except re.error:
                hit = False
            if hit and db.get(Finish, rule.get("finish_id")):
                runner.upsert_assignment(db, model_id, kind, name, rule["finish_id"])
                matches.append({"target_kind": kind, "target_name": name,
                                "finish_id": rule["finish_id"]})
                break
    rows = db.query(Assignment).filter(Assignment.model_id == model_id).all()
    return {"applied": len(matches), "matches": matches,
            "assignments": [assignment_out(a, db) for a in rows]}
