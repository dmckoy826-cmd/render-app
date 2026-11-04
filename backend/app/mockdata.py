"""Mock model-structure generator.

Stands in for the real Rhino worker's "analyze" step: given a model name it produces a
plausible structure document (layers, block definitions, parts with bounding boxes) in
the exact same contract the real worker will return, so the UI is fully exercisable.

Structure contract (also produced by worker/rhino_scripts/analyze_model.py):
{
  "units": "inches",
  "extents": {"min": [x,y,z], "max": [x,y,z]},
  "layers":  [{"name", "color", "part_count"}],
  "blocks":  [{"name", "instance_count", "layers", "part_ids"}],
  "parts":   [{"id", "name", "layer", "block", "requires_block_edit",
               "bbox": {"min": [...], "max": [...]}}]
}
"""
from __future__ import annotations

import colorsys
import hashlib
import random

_COLOR_KEYS = [
    ("WALNUT", "#6f4a2f"), ("WHITEOAK", "#c9a97a"), ("OAK", "#c9a97a"),
    ("MAPLE", "#e3c99a"), ("CHERRY", "#8a4a35"), ("GRAPHITE", "#4a4d52"),
    ("DOVE", "#cfd3d6"), ("CHARCOAL", "#3b3e42"), ("BLACK", "#26282d"),
    ("NAVY", "#2e3a52"), ("FOREST", "#2f4438"), ("GREY", "#7d8288"),
    ("GRAY", "#7d8288"), ("BRUSHED", "#aeb4b9"), ("STAINLESS", "#aeb4b9"),
    ("BRONZE", "#8c6a4f"), ("BRASS", "#b08d57"), ("MET", "#9aa0a6"),
    ("WHITE", "#e8e6e1"), ("PET", "#5b6770"), ("LAM", "#b08968"),
]


def layer_color(name: str) -> str:
    up = name.upper()
    for key, col in _COLOR_KEYS:
        if key in up:
            return col
    h = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, 0.42, 0.62)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def _part(pid: str, name: str, layer: str, x, y, z, block: str | None = None,
          rbe: bool = False) -> dict:
    return {
        "id": pid, "name": name, "layer": layer, "block": block,
        "requires_block_edit": rbe,
        "bbox": {"min": [x[0], y[0], z[0]], "max": [x[1], y[1], z[1]]},
    }


def _assemble(name: str, parts: list[dict], blocks: list[tuple[str, int]]) -> dict:
    mins = [p["bbox"]["min"] for p in parts]
    maxs = [p["bbox"]["max"] for p in parts]
    extents = {"min": [min(m[i] for m in mins) for i in range(3)],
               "max": [max(m[i] for m in maxs) for i in range(3)]}
    layers: list[dict] = []
    seen: dict[str, dict] = {}
    for p in parts:
        ln = p["layer"]
        if ln not in seen:
            seen[ln] = {"name": ln, "color": layer_color(ln), "part_count": 0}
            layers.append(seen[ln])
        seen[ln]["part_count"] += 1
    blocks_out = []
    for bname, count in blocks:
        bparts = [p for p in parts if p.get("block") == bname]
        blocks_out.append({
            "name": bname,
            "instance_count": count,
            "layers": sorted({p["layer"] for p in bparts}),
            "part_ids": [p["id"] for p in bparts],
        })
    return {
        "units": "inches",
        "source_file": name,
        "analyzer": "mock-engine 1.0 (simulated Rhino import)",
        "extents": extents,
        "layers": layers,
        "blocks": blocks_out,
        "parts": parts,
    }


def _desk(name: str) -> dict:
    p: list[dict] = []
    i = 0

    def add(nm, layer, x, y, z, block=None, rbe=False):
        nonlocal i
        i += 1
        p.append(_part(f"p{i:03d}", nm, layer, x, y, z, block, rbe))

    add("Counter Top", "LAM-WALNUT-TOP", (-48, 48), (-15, 15), (40.5, 42))
    add("Transaction Front", "LAM-WALNUT-FRONT", (-48, 48), (-15, -14.25), (3, 40.5))
    add("Left End Panel", "LAM-WALNUT-FRONT", (-48, -47.25), (-15, 15), (3, 40.5))
    add("Right End Panel", "LAM-WALNUT-FRONT", (47.25, 48), (-15, 15), (3, 40.5))
    add("Acoustic Accent Panel", "PET-CHARCOAL-ACCENT", (-30, 30), (-15.15, -15.0), (10, 34))
    add("Work Surface", "LAM-WHITEOAK-WORK", (-46.5, 46.5), (-14.25, 14.25), (28.75, 29.5))
    add("Modesty Panel", "PET-BLACK-MODESTY", (-44, 44), (13.5, 14.25), (3, 28.75))
    add("Base Plinth", "MET-BRUSHED-BASE", (-47.25, 47.25), (-14.25, 14.25), (0, 3))
    add("Pull Rail", "MET-BRUSHED-TRIM", (-12, 12), (-15.5, -15.15), (29.8, 30.4))
    for n, (ix, iy) in enumerate([(-32, 8), (32, 8)], start=1):
        add(f"Leg Post — SUPPORT-LEG #{n}", "MET-BRUSHED-TRIM",
            (ix - 1.5, ix + 1.5), (iy - 1.5, iy + 1.5), (3, 28.75), block="SUPPORT-LEG", rbe=True)
        add(f"Leg Foot — SUPPORT-LEG #{n}", "MET-BRUSHED-BASE",
            (ix - 6, ix + 6), (iy - 6, iy + 6), (3, 3.6), block="SUPPORT-LEG", rbe=True)
    return _assemble(name, p, [("SUPPORT-LEG", 2)])


def _cabinet(name: str) -> dict:
    p: list[dict] = []
    i = 0

    def add(nm, layer, x, y, z, block=None, rbe=False):
        nonlocal i
        i += 1
        p.append(_part(f"p{i:03d}", nm, layer, x, y, z, block, rbe))

    add("Left Side", "LAM-WHITEOAK-CASE", (0, 0.75), (0, 24), (3, 84))
    add("Right Side", "LAM-WHITEOAK-CASE", (35.25, 36), (0, 24), (3, 84))
    add("Top", "LAM-WHITEOAK-CASE", (0, 36), (0, 24), (83.25, 84))
    add("Bottom", "LAM-WHITEOAK-CASE", (0, 36), (0, 24), (3, 3.75))
    add("Back Panel", "PET-BLACK-BACK", (0.75, 35.25), (23.25, 24), (3.75, 83.25))
    add("Toe Kick", "MET-BRUSHED-BASE", (1, 35), (2, 24), (0, 3))
    for n, zz in enumerate((24, 44, 64), start=1):
        add(f"Shelf {n} — SHELF-ASSY #{n}", "LAM-WHITEOAK-CASE",
            (0.75, 35.25), (0.75, 23.25), (zz, zz + 0.75), block="SHELF-ASSY", rbe=True)
    add("Drawer Front (upper)", "PET-CHARCOAL-DRAWER", (0.9, 35.1), (-0.75, 0), (15.75, 26.5))
    add("Drawer Front (lower)", "PET-CHARCOAL-DRAWER", (0.9, 35.1), (-0.75, 0), (4, 15))
    add("Door Left", "LAM-WALNUT-DOOR", (0.9, 17.85), (-0.75, 0), (27.5, 82.5))
    add("Door Right", "LAM-WALNUT-DOOR", (18.15, 35.1), (-0.75, 0), (27.5, 82.5))
    add("Drawer Pull (upper)", "MET-BRUSHED-PULL", (15, 21), (-1.35, -0.75), (20.6, 21.2))
    add("Drawer Pull (lower)", "MET-BRUSHED-PULL", (15, 21), (-1.35, -0.75), (9.4, 10))
    add("Door Pull Left", "MET-BRUSHED-PULL", (15.6, 16.2), (-1.35, -0.75), (52, 58))
    add("Door Pull Right", "MET-BRUSHED-PULL", (19.8, 20.4), (-1.35, -0.75), (52, 58))
    return _assemble(name, p, [("SHELF-ASSY", 3)])


_WOODS = ["WALNUT", "WHITEOAK", "MAPLE", "CHERRY", "GRAPHITE", "DOVE"]
_ACCENTS = ["CHARCOAL", "BLACK", "GREY", "NAVY", "FOREST"]
_METALS = ["BRUSHED", "BLACK", "BRONZE"]


def _generic(name: str) -> dict:
    h = hashlib.md5(name.encode()).hexdigest()
    rng = random.Random(h)
    wood = rng.choice(_WOODS)
    wood2 = rng.choice([w for w in _WOODS if w != wood])
    accent = rng.choice(_ACCENTS)
    metal = rng.choice(_METALS)
    W = round(rng.uniform(30, 72), 2)
    D = round(rng.uniform(18, 30), 2)
    H = round(rng.uniform(32, 84), 2)
    t = 0.75
    p: list[dict] = []
    i = 0

    def add(nm, layer, x, y, z, block=None, rbe=False):
        nonlocal i
        i += 1
        p.append(_part(f"p{i:03d}", nm, layer, x, y, z, block, rbe))

    add("Toe Kick", f"MET-{metal}-BASE", (1, W - 1), (2, D), (0, 3))
    add("Left Side", f"LAM-{wood}-CASE", (0, t), (0, D), (3, H))
    add("Right Side", f"LAM-{wood}-CASE", (W - t, W), (0, D), (3, H))
    add("Top", f"LAM-{wood2}-TOP", (0, W), (0, D), (H - t, H))
    add("Bottom", f"LAM-{wood}-CASE", (0, W), (0, D), (3, 3 + t))
    add("Back Panel", f"PET-BLACK-BACK", (t, W - t), (D - t / 2, D), (3 + t, H - t))
    add("Accent Band", f"PET-{accent}-ACCENT", (t, W - t), (-0.1, 0), (H * 0.55, H * 0.68))
    add("Door Left", f"LAM-{wood2}-DOOR", (t + 0.1, W / 2 - 0.15), (-t, 0), (3 + t + 0.2, H * 0.52))
    add("Door Right", f"LAM-{wood2}-DOOR", (W / 2 + 0.15, W - t - 0.1), (-t, 0), (3 + t + 0.2, H * 0.52))
    add("Pull Left", f"MET-{metal}-PULL", (W / 2 - 2.6, W / 2 - 2), (-t - 0.6, -t), (H * 0.34, H * 0.40))
    add("Pull Right", f"MET-{metal}-PULL", (W / 2 + 2, W / 2 + 2.6), (-t - 0.6, -t), (H * 0.34, H * 0.40))
    for n, zz in enumerate((3 + t + (H - 3 - 2 * t) * 0.33, 3 + t + (H - 3 - 2 * t) * 0.66), start=1):
        add(f"Shelf {n} — SHELF-ASSY #{n}", f"LAM-{wood}-CASE",
            (t, W - t), (t / 2, D - t), (zz, zz + t), block="SHELF-ASSY", rbe=True)
    return _assemble(name, p, [("SHELF-ASSY", 2)])


def build_structure(name: str) -> dict:
    low = (name or "").lower()
    if any(k in low for k in ("desk", "reception", "counter", "checkout", "teller", "kiosk")):
        return _desk(name)
    if any(k in low for k in ("cab", "millwork", "casework", "closet", "wardrobe",
                              "storage", "cubby", "locker", "shelf", "bookcase")):
        return _cabinet(name)
    return _generic(name)
