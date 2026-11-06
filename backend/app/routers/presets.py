"""Reusable finish-mapping presets (rule lists: name pattern -> finish)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

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
    """Save layer/block rules and exact, stable part identities without widening scope."""
    m = db.get(ModelDoc, body.model_id)
    if not m:
        raise HTTPException(404, "model not found")
    assignments = db.query(Assignment).filter(Assignment.model_id == m.id).all()
    if not assignments:
        raise HTTPException(409, "model has no assignments to save")
    struct = m.structure or {}
    stable = struct.get("target_schema") == "rhino-geometry-v1"
    valid = {
        "layer": {layer["name"] for layer in struct.get("layers", [])},
        "block": {block["name"] for block in struct.get("blocks", [])},
        "part": {p["id"] if stable else p["name"] for p in struct.get("parts", [])},
    }
    rules = []
    for a in assignments:
        if a.target_name not in valid.get(a.target_kind, set()):
            raise HTTPException(409, f"Cannot save stale {a.target_kind} target '{a.target_name}'; clear or remap it first")
        kind = a.target_kind
        target_property = "identity" if kind == "part" and stable else "name"
        rules.append({"match": "exact", "pattern": a.target_name, "finish_id": a.finish_id,
                      "target_kind": kind, "target_property": target_property,
                      "scale_width": a.scale_width, "scale_height": a.scale_height})
    p = Preset(name=body.name.strip() or f"{m.name} preset",
               description=body.description or f"Saved from model '{m.name}'", rules=rules)
    db.add(p)
    db.commit()
    db.refresh(p)
    return preset_out(p, db)
