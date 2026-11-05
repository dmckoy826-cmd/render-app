"""Models: upload CAD files, inspect analyzed structure, map finishes, auto-match."""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import automatch, runner
from ..config import MEDIA_DIR, MODEL_DIR, geometry_file_from_url
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
        "analyzer": s.get("analyzer", ""),
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
    import shutil
    orig = file.filename or "model.dwg"
    ext = ("." + orig.rsplit(".", 1)[-1].lower()) if "." in orig else ""
    if ext not in MODEL_EXT:
        raise HTTPException(400, f"unsupported file type '{ext}'. Accepted: {', '.join(sorted(MODEL_EXT))}")
    stem = f"{uuid.uuid4().hex[:10]}_{_safe_name(orig)}"
    rel = f"models/{stem}"
    dest = MEDIA_DIR / rel
    with open(dest, "wb") as out_fh:
        shutil.copyfileobj(file.file, out_fh, length=1024 * 1024)
    size_bytes = dest.stat().st_size
    if size_bytes == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "empty file")

    display = (name or "").strip() or re.sub(r"\.[^.]+$", "", orig)
    m = ModelDoc(name=display, original_name=orig, storage_path=rel,
                 content_type=file.content_type or "application/octet-stream",
                 size_bytes=size_bytes, status="uploaded")
    db.add(m)
    db.commit()
    db.refresh(m)
    job = runner.create_job(db, "analyze", m.id)
    return {"model": model_out(m), "job": job_out(job, db)}


@router.post("/from-path")
def upload_model_from_local_path(body: dict, db: Session = Depends(get_db)):
    import os
    from pathlib import Path
    import shutil
    raw_path = str(body.get("path") or "").strip().strip('"')
    if not raw_path or not os.path.isfile(raw_path):
        raise HTTPException(400, f"Local file not found: {raw_path}")
    src = Path(raw_path)
    orig = src.name
    ext = src.suffix.lower()
    if ext not in MODEL_EXT:
        raise HTTPException(400, f"unsupported file type '{ext}'. Accepted: {', '.join(sorted(MODEL_EXT))}")
    size_bytes = src.stat().st_size
    if size_bytes == 0:
        raise HTTPException(400, "empty file")
    stem = f"{uuid.uuid4().hex[:10]}_{_safe_name(orig)}"
    rel = f"models/{stem}"
    dest = MEDIA_DIR / rel
    try:
        os.link(src, dest)
    except OSError:
        shutil.copyfile(src, dest)
    display = str(body.get("name") or "").strip() or re.sub(r"\.[^.]+$", "", orig)
    m = ModelDoc(name=display, original_name=orig, storage_path=rel,
                 content_type="application/octet-stream",
                 size_bytes=size_bytes, status="uploaded")
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
        geometry_url = (m.structure or {}).get("geometry_url", "")
        geometry_file = geometry_file_from_url(geometry_url)
        if geometry_file is not None:
            geometry_file.unlink(missing_ok=True)
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
        structure = m.structure or {}
        if body.target_kind == "part":
            valid = {p["id"] if structure.get("target_schema") == "rhino-geometry-v1" else p["name"]
                     for p in structure.get("parts", [])}
        else:
            valid = {entry["name"] for entry in structure.get(body.target_kind + "s", [])}
        if body.target_name not in valid:
            raise HTTPException(409, "Target is missing or stale; re-analyze and select a current target.")
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
    out = []
    for kind, name in _targets(m):
        for s in automatch.suggest([name], finishes, min_score=min_score):
            out.append({"target_kind": kind, "target_name": name,
                        "finish_id": s["finish"].id, "finish": finish_out(s["finish"]),
                        "score": s["score"]})
    out.sort(key=lambda item: item["score"], reverse=True)
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
    existing = {(a.target_kind, a.target_name) for a in
                db.query(Assignment).filter(Assignment.model_id == model_id).all()}
    targets = [(kind, name, name) for kind, name in _targets(m)]
    struct = m.structure or {}
    targets += [("part", p["name"], p["id"] if struct.get("target_schema") == "rhino-geometry-v1" else p["name"])
                for p in struct.get("parts", [])]
    for kind, name, target in targets:
        if not body.overwrite and (kind, target) in existing:
            continue
        for rule in preset.rules or []:
            if rule.get("target_kind", "layer") != kind:
                continue
            pattern = rule.get("pattern", "")
            match_name = target if rule.get("target_property") == "identity" else name
            mode = rule.get("match", "contains")
            hit = False
            try:
                if mode == "exact":
                    hit = match_name.upper() == pattern.upper()
                elif mode == "starts_with":
                    hit = match_name.upper().startswith(pattern.upper())
                elif mode == "regex":
                    hit = re.search(pattern, match_name, re.IGNORECASE) is not None
                else:
                    hit = pattern.upper() in match_name.upper()
            except re.error:
                hit = False
            if hit and db.get(Finish, rule.get("finish_id")):
                runner.upsert_assignment(db, model_id, kind, target, rule["finish_id"],
                                         rule.get("scale_multiplier", 1.0))
                matches.append({"target_kind": kind, "target_name": target,
                                "finish_id": rule["finish_id"]})
                break
    rows = db.query(Assignment).filter(Assignment.model_id == model_id).all()
    return {"applied": len(matches), "matches": matches,
            "assignments": [assignment_out(a, db) for a in rows]}
