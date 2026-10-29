"""Rendered results gallery."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import MEDIA_DIR
from ..db import get_db
from ..models import Job, ModelDoc, Render

router = APIRouter(prefix="/api/renders", tags=["renders"])


def render_out(r: Render, db: Session) -> dict:
    m = db.get(ModelDoc, r.model_id)
    j = db.get(Job, r.job_id)
    return {
        "id": r.id,
        "job_id": r.job_id,
        "model_id": r.model_id,
        "model_name": m.name if m else "?",
        "image_url": f"/media/{r.image_path}",
        "width": r.width,
        "height": r.height,
        "camera": r.camera,
        "quality": (j.settings or {}).get("quality", "standard") if j else "standard",
        "duration_s": r.duration_s,
        "finishes": r.finishes_snapshot,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("")
def list_renders(model_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Render)
    if model_id:
        q = q.filter(Render.model_id == model_id)
    return [render_out(r, db) for r in q.order_by(Render.created_at.desc()).all()]


@router.get("/{render_id}")
def get_render(render_id: int, db: Session = Depends(get_db)):
    r = db.get(Render, render_id)
    if not r:
        raise HTTPException(404, "render not found")
    return render_out(r, db)


@router.delete("/{render_id}")
def delete_render(render_id: int, db: Session = Depends(get_db)):
    r = db.get(Render, render_id)
    if not r:
        raise HTTPException(404, "render not found")
    try:
        (MEDIA_DIR / r.image_path).unlink(missing_ok=True)
    except OSError:
        pass
    db.delete(r)
    db.commit()
    return {"ok": True}
