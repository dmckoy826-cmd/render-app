"""Reusable finish-mapping presets (rule lists: name pattern -> finish)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import automatch
from ..db import get_db
from ..models import Assignment, Finish, ModelDoc, Preset
from ..schemas import PresetFromModelIn, PresetIn

router = APIRouter(prefix="/api/presets", tags=["presets"])


def preset_out(p: Preset, db: Session) -> dict:
    rules = []
    for r in p.rules or []:
        f = db.get(Finish, r.get("finish_id"))
        rules.append({**r, "finish_name": f.name if f else "(deleted)",
                      "finish_thumb": (f"/media/{f.thumb_path}" if f and f.thumb_path
                                       else (f"/media/{f.storage_path}" if f else ""))})
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "rules": rules, "rule_count": len(rules),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("")
def list_presets(db: Session = Depends(get_db)):
    return [preset_out(p, db) for p in db.query(Preset).order_by(Preset.created_at.desc()).all()]


@router.post("")
def create_preset(body: PresetIn, db: Session = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(400, "name required")
    for r in body.rules:
        if not db.get(Finish, r.finish_id):
            raise HTTPException(404, f"finish {r.finish_id} not found")
    p = Preset(name=body.name.strip(), description=body.description,
               rules=[r.model_dump() for r in body.rules])
    db.add(p)
    db.commit()
    db.refresh(p)
    return preset_out(p, db)


@router.patch("/{preset_id}")
def patch_preset(preset_id: int, body: PresetIn, db: Session = Depends(get_db)):
    p = db.get(Preset, preset_id)
    if not p:
        raise HTTPException(404, "preset not found")
    for r in body.rules:
        if not db.get(Finish, r.finish_id):
            raise HTTPException(404, f"finish {r.finish_id} not found")
    p.name = body.name.strip() or p.name
    p.description = body.description
    p.rules = [r.model_dump() for r in body.rules]
    db.commit()
    db.refresh(p)
    return preset_out(p, db)


@router.delete("/{preset_id}")
def delete_preset(preset_id: int, db: Session = Depends(get_db)):
    p = db.get(Preset, preset_id)
    if not p:
        raise HTTPException(404, "preset not found")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/from-model")
def preset_from_model(body: PresetFromModelIn, db: Session = Depends(get_db)):
    """Save a model's current layer assignments as a reusable preset.

    Rule patterns use each layer's most distinctive token (e.g. LAM-WALNUT-FRONT -> "WALNUT")
    so the preset keeps working across similar drawings.
    """
    m = db.get(ModelDoc, body.model_id)
    if not m:
        raise HTTPException(404, "model not found")
    assignments = db.query(Assignment).filter(
        Assignment.model_id == m.id, Assignment.target_kind == "layer").all()
    if not assignments:
        raise HTTPException(409, "model has no layer assignments to save")
    rules, seen = [], set()
    for a in assignments:
        pattern = automatch.suggest_pattern(a.target_name)
        if pattern in seen:
            pattern = a.target_name  # fall back to exact layer name
        seen.add(pattern)
        rules.append({"match": "contains", "pattern": pattern,
                      "finish_id": a.finish_id, "target_kind": "layer"})
    p = Preset(name=body.name.strip() or f"{m.name} preset",
               description=body.description or f"Saved from model '{m.name}'", rules=rules)
    db.add(p)
    db.commit()
    db.refresh(p)
    return preset_out(p, db)
