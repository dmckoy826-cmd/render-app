"""SQLAlchemy ORM models."""
import datetime as dt

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Finish(Base):
    """A laminate / PET / product-finish swatch image with real-world scale."""
    __tablename__ = "finishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    # laminate | pet | product_finish | other
    category: Mapped[str] = mapped_column(String(40), default="laminate")
    original_name: Mapped[str] = mapped_column(String(300), default="")
    storage_path: Mapped[str] = mapped_column(String(500))   # relative to MEDIA_DIR
    thumb_path: Mapped[str] = mapped_column(String(500), default="")
    content_type: Mapped[str] = mapped_column(String(80), default="image/png")
    # Real-world size the swatch image represents, in inches (drives texture scaling)
    swatch_width_in: Mapped[float] = mapped_column(Float, default=24.0)
    swatch_height_in: Mapped[float] = mapped_column(Float, default=24.0)
    seamless: Mapped[bool] = mapped_column(Boolean, default=True)
    tags: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelDoc(Base):
    """An uploaded 3D model (DWG/DXF/3DM/SKP/OBJ/STEP/...) and its analyzed structure."""
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    original_name: Mapped[str] = mapped_column(String(300), default="")
    storage_path: Mapped[str] = mapped_column(String(500), default="")
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # uploaded | analyzing | ready | failed
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    units: Mapped[str] = mapped_column(String(20), default="inches")
    structure: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    preview_path: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Assignment(Base):
    """Finish -> model target mapping (a layer, a block definition, or one part)."""
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("model_id", "target_kind", "target_name",
                                       name="uq_assignment_target"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), index=True)
    # layer | block | part
    target_kind: Mapped[str] = mapped_column(String(20), default="layer")
    target_name: Mapped[str] = mapped_column(String(300))
    finish_id: Mapped[int] = mapped_column(ForeignKey("finishes.id"))
    # Optional per-target scale multiplier (1.0 = use finish's real-world swatch size)
    scale_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Preset(Base):
    """Reusable finish-mapping preset: rules that map layer/block name patterns to finishes."""
    __tablename__ = "presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    # [{match: contains|starts_with|exact|regex, pattern, finish_id, target_kind}]
    rules: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    """A queued unit of work: model analysis or a V-Ray render."""
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # analyze | render
    kind: Mapped[str] = mapped_column(String(20), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), index=True)
    # queued | running | done | failed | canceled
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(200), default="")
    runner: Mapped[str] = mapped_column(String(20), default="mock")  # mock | agent
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Render(Base):
    """A finished render image produced by a render job."""
    __tablename__ = "renders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), index=True)
    image_path: Mapped[str] = mapped_column(String(500))  # relative to MEDIA_DIR
    width: Mapped[int] = mapped_column(Integer, default=1920)
    height: Mapped[int] = mapped_column(Integer, default=1080)
    camera: Mapped[str] = mapped_column(String(20), default="iso")
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    # Snapshot of what was applied: [{finish_id, name, category, thumb, targets:[...]}]
    finishes_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
