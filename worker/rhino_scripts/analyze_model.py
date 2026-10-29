"""Rhino 8 headless: analyze a CAD model into the FinishFlow structure contract.

Run by worker/agent.py inside Rhino (RhinoPython). Reads:
    FF_MODEL     path to the imported CAD file (DWG/DXF/3DM/SKP/...)
    FF_OUT_JSON  where to write the structure JSON
    FF_OUT_PNG   where to write a shaded viewport preview

Structure contract (must match backend/app/mockdata.py):
    {"units", "extents": {min,max}, "layers": [{name,color,part_count}],
     "blocks": [{name,instance_count,layers,part_ids}],
     "parts": [{id,name,layer,block,requires_block_edit,bbox:{min,max}}]}
"""
import json
import os

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import System.Drawing.Color

MODEL = os.environ["FF_MODEL"]
OUT_JSON = os.environ["FF_OUT_JSON"]
OUT_PNG = os.environ.get("FF_OUT_PNG", "")


def layer_color_hex(name):
    c = rs.LayerColor(name)
    return "#%02x%02x%02x" % (c.R, c.G, c.B)


def main():
    rs.EnableRedraw(False)
    ok = rs.OpenFileName
    # Import the CAD file (DWG/DXF/3DM/SKP/OBJ/STEP all route through Rhino's importers)
    rs.Command(f'-_Import "{MODEL}" _Enter', False)
    rs.EnableRedraw(True)

    units = str(sc.doc.ModelUnitSystem)  # e.g. "Inches" / "Millimeters"
    parts, blocks_meta = [], {}
    for obj in rs.AllObjects():
        if not rs.IsSurface(obj) and not rs.IsPolysurface(obj) and not rs.IsMesh(obj):
            continue
        bb = rs.BoundingBox(obj)
        if not bb:
            continue
        layer = rs.ObjectLayer(obj) or "0"
        block_name = None
        rbe = False
        parent = rs.ObjectParentObject(obj)
        if parent:  # instance reference -> part lives in a block definition
            block_name = rs.BlockInstanceName(parent)
            rbe = True
            defn = rs.BlockInstanceName(parent, True)
            blocks_meta.setdefault(defn, {"count": 0, "ids": []})
            blocks_meta[defn]["count"] += 1
        pid = f"p{len(parts) + 1:03d}"
        parts.append({
            "id": pid,
            "name": rs.ObjectName(obj) or f"{layer} #{len(parts) + 1}",
            "layer": layer,
            "block": block_name,
            "requires_block_edit": rbe,
            "bbox": {"min": [bb[0].X, bb[0].Y, bb[0].Z], "max": [bb[1].X, bb[1].Y, bb[1].Z]},
        })
        if block_name:
            blocks_meta.setdefault(block_name, {"count": 1, "ids": []})
            blocks_meta[block_name]["ids"].append(pid)

    layer_info, seen = [], set()
    for p in parts:
        if p["layer"] not in seen:
            seen.add(p["layer"])
            layer_info.append({"name": p["layer"], "color": layer_color_hex(p["layer"]),
                               "part_count": sum(1 for q in parts if q["layer"] == p["layer"])})
    blocks = [{"name": n, "instance_count": max(1, v["count"] // max(1, len(v["ids"]) or 1)),
               "layers": sorted({p["layer"] for p in parts if p["id"] in v["ids"]}),
               "part_ids": v["ids"]} for n, v in blocks_meta.items()]

    mins = [p["bbox"]["min"] for p in parts] or [[0, 0, 0]]
    maxs = [p["bbox"]["max"] for p in parts] or [[0, 0, 0]]
    structure = {
        "units": "inches" if units.lower().startswith("inch") else units.lower(),
        "source_file": os.path.basename(MODEL),
        "analyzer": "rhino8-worker 1.0",
        "extents": {"min": [min(m[i] for m in mins) for i in range(3)],
                    "max": [max(m[i] for m in maxs) for i in range(3)]},
        "layers": layer_info,
        "blocks": blocks,
        "parts": parts,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(structure, fh)

    if OUT_PNG:
        rs.Command("-_SetCurrentMode _Shaded _Enter", False)
        rs.Command("-_Zoom _Extents _Enter", False)
        rs.ViewCaptureToFile(OUT_PNG, 1200, 900)
    print("ANALYZE_OK", len(parts), "parts")


main()
