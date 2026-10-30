"""Rhino 8: analyze a CAD model into the FinishFlow structure contract.

Run by worker/agent.py inside Rhino (RhinoPython). Reads:
    FF_MODEL     path to the imported CAD file (DWG/DXF/3DM/SKP/OBJ/STEP/...)
    FF_OUT_JSON  where to write the structure JSON
    FF_OUT_PNG   where to write a shaded viewport preview

Structure contract (identical to backend mock/dxf-parser output):
    {"units", "extents": {min,max}, "layers": [{name,color,part_count}],
     "blocks": [{name,instance_count,layers,part_ids}],
     "parts": [{id,name,layer,block,requires_block_edit,bbox:{min,max}}]}

Notes:
  * Block instances become one part each with requires_block_edit=True, so the UI can
    target finishes inside block definitions (the scripted equivalent of BlockEdit).
  * All coordinates are converted to INCHES (the app's texture-scale unit) regardless
    of the drawing's unit system.
  * The document's Modified flag is cleared before exit so agent.py's `_Exit` macro
    never blocks on a save prompt.
"""
import json
import os
import sys
import traceback

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino

MODEL = os.environ["FF_MODEL"]
OUT_JSON = os.environ["FF_OUT_JSON"]
OUT_PNG = os.environ.get("FF_OUT_PNG", "")
MAX_PARTS = 800


def layer_color_hex(name):
    try:
        c = rs.LayerColor(name)
        if c:
            return "#%02x%02x%02x" % (c.R, c.G, c.B)
    except Exception:
        pass
    return "#8d929a"


def bbox_in(obj, scale):
    bb = rs.BoundingBox(obj)
    if not bb:
        return None
    xs = [p.X * scale for p in bb]
    ys = [p.Y * scale for p in bb]
    zs = [p.Z * scale for p in bb]
    return {"min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]}


def main():
    rs.EnableRedraw(False)
    # Import routes DWG/DXF/3DM/SKP/OBJ/STEP/IGES/SAT through Rhino's own importers
    ok = rs.Command('-_Import "%s" _Enter' % MODEL, False)
    rs.EnableRedraw(True)
    if ok is False and not rs.AllObjects():
        raise RuntimeError("Rhino could not import: %s" % MODEL)

    # everything -> inches (FinishFlow scales textures in inches)
    scale = Rhino.RhinoMath.UnitScale(sc.doc.ModelUnitSystem, Rhino.UnitSystem.Inches)

    # ObjectType bits: surface=8, polysurface=16, mesh=32, extrusion=2^30, subd=2^31
    SOLID_MASK = 8 | 16 | 32 | 1073741824 | 2147483648
    CURVE_MASK = 4

    def union(a, b):
        if a is None:
            return b
        return {"min": [min(a["min"][i], b["min"][i]) for i in range(3)],
                "max": [max(a["max"][i], b["max"][i]) for i in range(3)]}

    parts, block_parts, curve_layers = [], {}, {}
    for obj in rs.AllObjects():
        is_inst = rs.IsBlockInstance(obj)
        otype = rs.ObjectType(obj) or 0
        if not (is_inst or (otype & SOLID_MASK) or (otype & CURVE_MASK)):
            continue
        bb = bbox_in(obj, scale)
        if not bb:
            continue
        layer = rs.ObjectLayer(obj) or "0"
        if is_inst:
            if len(parts) >= MAX_PARTS:
                continue
            block_name = rs.BlockInstanceName(obj) or "BLOCK"
            block_parts.setdefault(block_name, []).append("p%03d" % (len(parts) + 1))
            parts.append({
                "id": "p%03d" % (len(parts) + 1),
                "name": rs.ObjectName(obj) or "%s #%d" % (block_name, len(block_parts[block_name])),
                "layer": layer,
                "block": block_name,
                "requires_block_edit": True,
                "bbox": bb,
            })
        elif otype & SOLID_MASK:
            if len(parts) >= MAX_PARTS:
                continue
            parts.append({
                "id": "p%03d" % (len(parts) + 1),
                "name": rs.ObjectName(obj) or "%s solid #%d" % (layer, len(parts) + 1),
                "layer": layer,
                "block": None,
                "requires_block_edit": False,
                "bbox": bb,
            })
        else:  # curves: group per layer into one part (2D drawing linework)
            curve_layers[layer] = union(curve_layers.get(layer), bb)
    for layer, bb in curve_layers.items():
        if len(parts) >= MAX_PARTS:
            break
        parts.append({
            "id": "p%03d" % (len(parts) + 1),
            "name": "%s linework" % layer,
            "layer": layer,
            "block": None,
            "requires_block_edit": False,
            "bbox": bb,
        })

    if not parts:
        raise RuntimeError("no usable geometry found in %s" % MODEL)

    layers, seen = [], set()
    for p in parts:
        if p["layer"] not in seen:
            seen.add(p["layer"])
            layers.append({"name": p["layer"], "color": layer_color_hex(p["layer"]),
                           "part_count": sum(1 for q in parts if q["layer"] == p["layer"])})

    blocks = []
    for name, ids in block_parts.items():
        blocks.append({
            "name": name,
            "instance_count": len(ids),
            "layers": sorted({p["layer"] for p in parts if p["id"] in ids}),
            "part_ids": ids,
        })

    mins = [p["bbox"]["min"] for p in parts]
    maxs = [p["bbox"]["max"] for p in parts]
    structure = {
        "units": "inches",
        "source_file": os.path.basename(MODEL),
        "analyzer": "rhino8-worker 1.0",
        "extents": {"min": [min(m[i] for m in mins) for i in range(3)],
                    "max": [max(m[i] for m in maxs) for i in range(3)]},
        "layers": layers,
        "blocks": blocks,
        "parts": parts,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(structure, fh)

    if OUT_PNG:
        try:
            rs.Command("-_SetCurrentView _World _Perspective _Enter", False)
            rs.ZoomExtents()
            rs.ViewCaptureToFile(OUT_PNG, 1200, 900)
        except Exception as exc:
            print("preview capture failed (non-fatal): %r" % exc)

    print("ANALYZE_OK %d parts, %d blocks, %d layers" % (len(parts), len(blocks), len(layers)))


try:
    main()
except Exception:
    print("ANALYZE_FAIL")
    traceback.print_exc()
    try:
        with open(OUT_JSON + ".error.txt", "w") as fh:
            fh.write(traceback.format_exc())
    except Exception:
        pass
    sys.exit(0)  # still exit 0; agent checks for structure.json and reports the failure
finally:
    try:
        sc.doc.Modified = False  # let _Exit close Rhino without a save prompt
    except Exception:
        pass
