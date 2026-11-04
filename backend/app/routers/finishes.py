"""Finish (swatch) library: upload PNG/JPG laminate, PET and product-finish images."""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import imaging
from ..config import FINISH_DIR, MEDIA_DIR, THUMB_DIR
from ..db import get_db
from ..models import Assignment, Finish

router = APIRouter(prefix="/api/finishes", tags=["finishes"])

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp"}


class FinishPatch(BaseModel):
    name: str | None = None
    category: str | None = None
    swatch_width_in: float | None = None
    swatch_height_in: float | None = None
    seamless: bool | None = None
    tags: str | None = None


def finish_out(f: Finish) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "category": f.category,
        "original_name": f.original_name,
        "image_url": f"/media/{f.storage_path}",
        "thumb_url": f"/media/{f.thumb_path}" if f.thumb_path else f"/media/{f.storage_path}",
        "swatch_width_in": f.swatch_width_in,
        "swatch_height_in": f.swatch_height_in,
        "seamless": f.seamless,
        "tags": f.tags,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[-80:]


@router.get("")
def list_finishes(category: str | None = None, q: str | None = None,
                  db: Session = Depends(get_db)):
    query = db.query(Finish)
    if category and category != "all":
        query = query.filter(Finish.category == category)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            Finish.name.ilike(like) | Finish.tags.ilike(like) | Finish.original_name.ilike(like))
    return [finish_out(f) for f in query.order_by(Finish.created_at.desc()).all()]


@router.get("/{finish_id}")
def get_finish(finish_id: int, db: Session = Depends(get_db)):
    f = db.get(Finish, finish_id)
    if not f:
        raise HTTPException(404, "finish not found")
    return finish_out(f)


@router.post("")
async def create_finish(
    file: UploadFile,
    name: str = Form(None),
    category: str = Form("laminate"),
    swatch_width_in: float = Form(24.0),
    swatch_height_in: float = Form(24.0),
    seamless: bool = Form(True),
    tags: str = Form(""),
    db: Session = Depends(get_db),
):
    orig = file.filename or "swatch.png"
    ext = ("." + orig.rsplit(".", 1)[-1].lower()) if "." in orig else ".png"
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"unsupported image type '{ext}' — use PNG, JPG or WEBP")
    if category not in ("laminate", "pet", "product_finish", "other"):
        raise HTTPException(400, "category must be laminate | pet | product_finish | other")
    if swatch_width_in <= 0 or swatch_height_in <= 0:
        raise HTTPException(400, "swatch dimensions must be positive")

    stem = f"{uuid.uuid4().hex[:10]}_{_safe_name(orig)}"
    if not stem.lower().endswith(tuple(ALLOWED_EXT)):
        stem = stem + ext
    rel = f"finishes/{stem}"
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    (MEDIA_DIR / rel).write_bytes(data)

    thumb_rel = f"thumbs/{stem}.jpg"
    try:
        imaging.make_thumbnail(str(MEDIA_DIR / rel), str(THUMB_DIR.parent / thumb_rel))
    except Exception:
        thumb_rel = ""

    display_name = (name or "").strip() or re.sub(r"\.[^.]+$", "", orig).replace("_", " ").replace("-", " ")
    f = Finish(name=display_name, category=category, original_name=orig, storage_path=rel,
               thumb_path=thumb_rel, content_type=file.content_type or "image/png",
               swatch_width_in=swatch_width_in, swatch_height_in=swatch_height_in,
               seamless=seamless, tags=tags.strip())
    db.add(f)
    db.commit()
    db.refresh(f)
    return finish_out(f)


@router.patch("/{finish_id}")
def patch_finish(finish_id: int, patch: FinishPatch, db: Session = Depends(get_db)):
    f = db.get(Finish, finish_id)
    if not f:
        raise HTTPException(404, "finish not found")
    data = patch.model_dump(exclude_none=True)
    if "swatch_width_in" in data and data["swatch_width_in"] <= 0:
        raise HTTPException(400, "swatch width must be positive")
    if "swatch_height_in" in data and data["swatch_height_in"] <= 0:
        raise HTTPException(400, "swatch height must be positive")
    if "category" in data and data["category"] not in ("laminate", "pet", "product_finish", "other"):
        raise HTTPException(400, "invalid category")
    for k, v in data.items():
        setattr(f, k, v)
    db.commit()
    db.refresh(f)
    return finish_out(f)


@router.delete("/{finish_id}")
def delete_finish(finish_id: int, db: Session = Depends(get_db)):
    f = db.get(Finish, finish_id)
    if not f:
        raise HTTPException(404, "finish not found")
    db.query(Assignment).filter(Assignment.finish_id == f.id).delete()
    db.delete(f)
    db.commit()
    for rel in (f.storage_path, f.thumb_path):
        try:
            if rel:
                (MEDIA_DIR / rel).unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True}
