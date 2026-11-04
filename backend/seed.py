"""Seed the database with a demo library so the UI is populated on first run.

Run:  cd backend && ../.venv/bin/python seed.py [--fresh]

  --fresh   wipe existing data first (DB + media)
"""
from __future__ import annotations

import shutil
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import config, imaging, mockdata, runner
from app.db import Base, SessionLocal, engine
from app.models import Assignment, Finish, Job, ModelDoc, Preset, Render

FINISHES = [
    ("Walnut Harvest Laminate", "laminate", "wood-walnut", (48, 96), "walnut,wood,brown,dark,grain"),
    ("White Oak Laminate", "laminate", "wood-oak", (48, 96), "oak,white oak,wood,light,grain"),
    ("Maple Laminate", "laminate", "wood-maple", (48, 96), "maple,wood,light,grain"),
    ("Cherry Laminate", "laminate", "wood-cherry", (48, 96), "cherry,wood,red,brown,grain"),
    ("Charcoal PET Felt", "pet", "felt-charcoal", (24, 24), "charcoal,felt,acoustic,grey,dark,pet"),
    ("Black Matte PET", "pet", "matte-black", (24, 24), "black,matte,pet,acoustic,felt"),
    ("Dove Grey PET Felt", "pet", "felt-dove", (24, 24), "dove,grey,light,felt,acoustic,pet"),
    ("Brushed Stainless", "product_finish", "metal-steel", (12, 12), "stainless,brushed,steel,metal,silver"),
    ("Anodized Bronze", "product_finish", "metal-bronze", (12, 12), "bronze,anodized,metal,warm"),
]

MODELS = [
    ("Reception Desk - 8ft", "Reception Desk - 8ft.dwg"),
    ("Storage Cabinet - 36in", "Storage Cabinet - 36in.dwg"),
]


def utcnow():
    return datetime.now(timezone.utc)


def seed(fresh: bool = False) -> None:
    if fresh and config.DATA_DIR.exists():
        print(f"--fresh: wiping {config.DATA_DIR}")
        shutil.rmtree(config.DATA_DIR)
    for d in (config.FINISH_DIR, config.THUMB_DIR, config.MODEL_DIR,
              config.PREVIEW_DIR, config.RENDER_DIR):
        d.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        if db.query(Finish).count() > 0 or db.query(ModelDoc).count() > 0:
            print("Database already has data — skipping seed (use --fresh to reset).")
            return

        # ---- finishes -----------------------------------------------------
        finish_rows: dict[str, Finish] = {}
        for name, category, kind, (sw, sh), tags in FINISHES:
            img = imaging.make_procedural_finish(kind)
            stem = f"{uuid.uuid4().hex[:10]}_{kind}.png"
            rel = f"finishes/{stem}"
            img.save(config.MEDIA_DIR / rel, "PNG")
            thumb_rel = f"thumbs/{stem}.jpg"
            imaging.make_thumbnail(str(config.MEDIA_DIR / rel), str(config.MEDIA_DIR / thumb_rel))
            f = Finish(name=name, category=category, original_name=f"{kind}.png",
                       storage_path=rel, thumb_path=thumb_rel, content_type="image/png",
                       swatch_width_in=sw, swatch_height_in=sh, seamless=True, tags=tags)
            db.add(f)
            db.commit()
            db.refresh(f)
            finish_rows[kind] = f
            print(f"  finish  #{f.id:>2}  {name}")

        # ---- models (analyzed, ready) --------------------------------------
        model_rows = []
        for display, orig in MODELS:
            blob = ("AC1032\n(demo placeholder — the mock engine synthesizes structure "
                    "from the file name)").encode()
            rel = f"models/{uuid.uuid4().hex[:10]}_{orig.replace(' ', '_')}"
            (config.MEDIA_DIR / rel).write_bytes(blob)
            m = ModelDoc(name=display, original_name=orig, storage_path=rel,
                         content_type="application/acad", size_bytes=len(blob),
                         status="uploaded")
            db.add(m)
            db.commit()
            db.refresh(m)
            structure = mockdata.build_structure(m.name)
            runner.apply_analysis(db, m, structure)
            analyze = Job(kind="analyze", model_id=m.id, status="done", progress=100,
                          stage="Complete", runner="mock",
                          created_at=m.created_at, started_at=m.created_at,
                          finished_at=m.created_at + timedelta(seconds=3))
            db.add(analyze)
            db.commit()
            model_rows.append(m)
            print(f"  model   #{m.id:>2}  {m.name}  ({len(structure['parts'])} parts, "
                  f"{len(structure['layers'])} layers)")

        # ---- auto-matched assignments ---------------------------------------
        for m in model_rows:
            n = runner.auto_assign_from_names(db, m, threshold=0.35, overwrite=True)
            print(f"  assign   →  {m.name}: {n} auto-matched")

        # ---- preset ------------------------------------------------------------
        preset = Preset(
            name="Walnut Line — Standard",
            description="House standard for the walnut casework line: walnut laminate faces, "
                        "white oak case/worksurfaces, charcoal PET accents, brushed stainless trim.",
            rules=[
                {"match": "contains", "pattern": "WALNUT", "finish_id": finish_rows["wood-walnut"].id, "target_kind": "layer"},
                {"match": "contains", "pattern": "WHITEOAK", "finish_id": finish_rows["wood-oak"].id, "target_kind": "layer"},
                {"match": "contains", "pattern": "CHARCOAL", "finish_id": finish_rows["felt-charcoal"].id, "target_kind": "layer"},
                {"match": "contains", "pattern": "BLACK", "finish_id": finish_rows["matte-black"].id, "target_kind": "layer"},
                {"match": "contains", "pattern": "BRUSHED", "finish_id": finish_rows["metal-steel"].id, "target_kind": "layer"},
                {"match": "contains", "pattern": "MET", "finish_id": finish_rows["metal-steel"].id, "target_kind": "layer"},
            ],
        )
        db.add(preset)
        db.commit()
        print(f"  preset  #{preset.id:>2}  {preset.name}")

        # ---- one finished render for the gallery --------------------------------
        desk = model_rows[0]
        job = Job(kind="render", model_id=desk.id, status="running", progress=97,
                  stage="V-Ray progressive render", runner="mock",
                  settings={"width": 1920, "height": 1080, "quality": "standard", "camera": "iso"},
                  created_at=utcnow() - timedelta(seconds=12),
                  started_at=utcnow() - timedelta(seconds=10))
        db.add(job)
        db.commit()
        db.refresh(job)
        r = runner.produce_render(db, job, desk)
        job.status = "done"
        job.progress = 100
        job.stage = "Complete"
        job.finished_at = utcnow()
        db.commit()
        print(f"  render  #{r.id:>2}  {r.image_path}  ({r.width}x{r.height})")

        print("\nSeed complete.")


if __name__ == "__main__":
    seed(fresh="--fresh" in sys.argv)
