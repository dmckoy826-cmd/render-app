"""True-geometry DXF parser (ezdxf).

Binary DWG cannot be read without Rhino/ODA, but AutoCAD's DXF export can: this module
produces the same structure contract as the Rhino worker and the mock engine, using the
file's real layers, block definitions (INSERT references) and entity bounding boxes.

The runner content-sniffs uploads: anything that is NOT binary DWG (AC10xx magic) is
offered to this parser first — so a DXF named ".dwg" still parses for real.
"""
from __future__ import annotations

import os

import ezdxf
from ezdxf import bbox as ezbbox
from ezdxf import colors as ezcolors

# $INSUNITS -> multiplier to inches
UNIT_TO_IN = {
    0: 1.0,   # unitless — assume inches
    1: 1.0,   # inches
    2: 12.0,  # feet
    4: 1 / 25.4,   # mm
    5: 1 / 2.54,   # cm
    6: 1 / 0.0254, # m
    14: 1 / 25.4,  # (legacy) mm
    21: 1 / 25.4,
}

MAX_PARTS = 800  # viewer sanity cap
MAX_VIRTUAL = 200_000  # guard against pathological block expansion
# annotation/text entities are not finishable geometry — skip them everywhere
SKIP_TYPES = {"ATTDEF", "ATTRIB", "TEXT", "MTEXT", "DIMENSION", "LEADER",
              "MULTILEADER", "TOLERANCE", "WIPEOUT", "LIGHT", "CAMERA"}


def _layer_hex(doc, name: str) -> str:
    try:
        lay = doc.layers.get(name)
        r, g, b = ezcolors.aci2rgb(int(lay.color) & 0xFF) if lay else (141, 146, 154)
        return "#%02x%02x%02x" % (r, g, b)
    except Exception:
        return "#8d929a"


def parse(path: str) -> dict:
    doc = ezdxf.readfile(path)  # raises on binary DWG / corrupt files
    msp = doc.modelspace()
    units = int(doc.header.get("$INSUNITS", 1) or 1)
    k = UNIT_TO_IN.get(units, 1.0)
    cache = ezbbox.Cache()

    parts: list[dict] = []
    blocks_meta: dict[str, dict] = {}
    layer_bbox: dict[str, list[float]] = {}

    def add_part(name, layer, block, rbe, mn, mx) -> str:
        pid = f"p{len(parts) + 1:03d}"
        parts.append({
            "id": pid,
            "name": name,
            "layer": layer,
            "block": block,
            "requires_block_edit": rbe,
            "bbox": {"min": [round(v * k, 3) for v in mn],
                     "max": [round(v * k, 3) for v in mx]},
        })
        return pid

    virtual_budget = MAX_VIRTUAL

    def union(cur, b):
        if cur is None:
            return [b.extmin.x, b.extmin.y, b.extmin.z, b.extmax.x, b.extmax.y, b.extmax.z]
        cur[0] = min(cur[0], b.extmin.x); cur[1] = min(cur[1], b.extmin.y)
        cur[2] = min(cur[2], b.extmin.z); cur[3] = max(cur[3], b.extmax.x)
        cur[4] = max(cur[4], b.extmax.y); cur[5] = max(cur[5], b.extmax.z)
        return cur

    for e in msp:
        if len(parts) >= MAX_PARTS:
            break
        try:
            if e.dxftype() == "INSERT":
                defn = e.dxf.name
                meta = blocks_meta.setdefault(defn, {"count": 0, "layers": set(), "part_ids": []})
                meta["count"] += 1
                n = meta["count"]
                # Expand the block definition (recursively — nested INSERTs too) into
                # world-space copies and group them by their REAL inner layers. This is
                # what makes drawings that are "4 inserts on layer 0" show their actual
                # structure (e.g. AFUWK-3-WKLM work surfaces, AFUWK-3-EDLM edges...).
                per_layer: dict[str, list] = {}
                expanded = 0
                try:
                    for ve in e.virtual_entities():
                        if virtual_budget <= 0 or expanded >= 5000:
                            break
                        virtual_budget -= 1
                        expanded += 1
                        if ve.dxftype() in SKIP_TYPES:
                            continue
                        b = ezbbox.extents([ve])
                        if not b.has_data:
                            continue
                        per_layer[getattr(ve.dxf, "layer", "0")] = union(
                            per_layer.get(getattr(ve.dxf, "layer", "0")), b)
                except Exception:
                    per_layer = {}
                if per_layer:
                    for lay, bb in per_layer.items():
                        if len(parts) >= MAX_PARTS:
                            break
                        meta["layers"].add(lay)
                        pid = add_part(f"{defn} #{n} · {lay}", lay, defn, True, bb[:3], bb[3:])
                        meta["part_ids"].append(pid)
                else:
                    # fallback: whole-instance bbox when expansion yields nothing
                    b = ezbbox.extents([e], cache=cache)
                    if not b.has_data:
                        continue
                    meta["layers"].add(e.dxf.layer)
                    pid = add_part(f"{defn} #{n}", e.dxf.layer, defn, True, b.extmin, b.extmax)
                    meta["part_ids"].append(pid)
            else:
                if e.dxftype() in SKIP_TYPES:
                    continue
                b = ezbbox.extents([e], cache=cache)
                if not b.has_data:
                    continue
                lay = e.dxf.layer
                cur = layer_bbox.get(lay)
                if cur is None:
                    layer_bbox[lay] = [b.extmin.x, b.extmin.y, b.extmin.z,
                                       b.extmax.x, b.extmax.y, b.extmax.z]
                else:
                    cur[0] = min(cur[0], b.extmin.x)
                    cur[1] = min(cur[1], b.extmin.y)
                    cur[2] = min(cur[2], b.extmin.z)
                    cur[3] = max(cur[3], b.extmax.x)
                    cur[4] = max(cur[4], b.extmax.y)
                    cur[5] = max(cur[5], b.extmax.z)
        except Exception:
            continue

    for lay, bb in layer_bbox.items():
        if len(parts) >= MAX_PARTS:
            break
        add_part(f"{lay} geometry", lay, None, False, bb[:3], bb[3:])

    if not parts:
        raise ValueError("no geometry with usable bounding boxes found in DXF")

    layer_parts: dict[str, int] = {}
    for p in parts:
        layer_parts[p["layer"]] = layer_parts.get(p["layer"], 0) + 1
    # include the file's real layer table (skip Defpoints) so the UI shows the
    # drawing's actual layer structure with AutoCAD colors, even for layers whose
    # geometry is annotation-only
    names = list(layer_parts)
    try:
        for lay in doc.layers:
            if lay.dxf.name != "Defpoints" and lay.dxf.name not in names:
                names.append(lay.dxf.name)
    except Exception:
        pass
    layers = [{"name": n, "color": _layer_hex(doc, n), "part_count": layer_parts.get(n, 0)}
              for n in names]
    blocks = [{"name": n, "instance_count": v["count"], "layers": sorted(v["layers"]),
               "part_ids": v["part_ids"]} for n, v in blocks_meta.items()]

    mins = [p["bbox"]["min"] for p in parts]
    maxs = [p["bbox"]["max"] for p in parts]
    return {
        "units": "inches",
        "source_file": os.path.basename(path),
        "analyzer": f"dxf-parser 1.0 (ezdxf {ezdxf.__version__}, $INSUNITS={units})",
        "extents": {"min": [min(m[i] for m in mins) for i in range(3)],
                    "max": [max(m[i] for m in maxs) for i in range(3)]},
        "layers": layers,
        "blocks": blocks,
        "parts": parts,
    }
