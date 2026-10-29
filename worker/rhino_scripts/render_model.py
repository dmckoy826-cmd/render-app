"""Rhino 8 headless: apply assigned finishes as V-Ray materials and render.

Run by worker/agent.py inside Rhino (RhinoPython). Reads:
    FF_MODEL        CAD file to open/import
    FF_ASSIGNMENTS  JSON list: [{target_kind, target_name, scale_multiplier,
                                  finish: {file_url, swatch_width_in, swatch_height_in,
                                           category, name}}]
    FF_OUT_DIR      folder for output images
    FF_WIDTH/FF_HEIGHT/FF_QUALITY/FF_CAMERA

Finish images are downloaded by the agent? No — file_url points at the server, so this
script fetches them with .NET WebClient (no extra deps inside Rhino).

Texture scaling: each finish image represents swatch_width_in x swatch_height_in of
real material, so the WCS box mapping size is set from those dims (x scale_multiplier).
Parts that live inside block definitions are handled by editing the block definition
(the scripted equivalent of BlockEdit): materials are assigned to the definition
geometry so every instance updates at once.
"""
import json
import os
import sys

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino

MODEL = os.environ["FF_MODEL"]
ASSIGN = os.environ["FF_ASSIGNMENTS"]
OUT_DIR = os.environ["FF_OUT_DIR"]
WIDTH = int(os.environ.get("FF_WIDTH", "1920"))
HEIGHT = int(os.environ.get("FF_HEIGHT", "1080"))
QUALITY = os.environ.get("FF_QUALITY", "standard")
CAMERA = os.environ.get("FF_CAMERA", "iso")

TEX_CACHE = {}


def fetch(url_rel):
    """Download a finish image from the FinishFlow server into a temp path."""
    import System.Net
    base = os.environ.get("FF_API", "http://localhost:8000")
    local = os.path.join(OUT_DIR, "tex_" + url_rel.replace("/", "_").replace("\\", "_"))
    if local not in TEX_CACHE:
        System.Net.WebClient().DownloadFile(base + url_rel, local)
        TEX_CACHE[local] = local
    return TEX_CACHE[local]


def make_material(name, img_path, sw_w, sw_h, metallic):
    """Create a Rhino render material with a bitmap texture at real-world scale.

    V-Ray for Rhino reads Rhino materials; for full V-Ray control swap this for the
    V-Ray Python API (vray module) — TODO: bind glossary/roughness per category.
    """
    mat = Rhino.DocObjects.Material()
    mat.Name = name
    idx = sc.doc.Materials.Add(mat)
    m = sc.doc.Materials[idx]
    m.SetBitmapTexture(True, img_path, True)
    # WCS box mapping with the swatch's real-world size => correct texture scale
    m.TextureMapping = Rhino.DocObjects.MaterialTextureMapping.NewWcsBoxMapping(
        True, sw_w, sw_h, max(sw_w, sw_h))
    if metallic:
        m.SetMetallic(0.85)
        m.Shine = 0.9
    sc.doc.Materials.Modify(m, idx, True)
    return idx


def assign_to_objects(objs, mat_idx):
    for o in objs:
        rs.ObjectMaterialSource(o, 1)  # material from object
        rs.ObjectMaterialIndex(o, mat_idx)


def main():
    rs.Command(f'-_Import "{MODEL}" _Enter', False)
    assignments = json.loads(open(ASSIGN).read())

    # group assignments into materials
    mats = {}
    for a in assignments:
        f = a["finish"]
        key = (f["id"], a.get("scale_multiplier", 1.0))
        if key not in mats:
            img = fetch(f["file_url"])
            mult = a.get("scale_multiplier", 1.0) or 1.0
            mats[key] = make_material(
                f"FF_{f['name']}", img,
                f["swatch_width_in"] * mult, f["swatch_height_in"] * mult,
                f.get("category") == "product_finish")

    layer_objs, block_defs, part_objs = {}, {}, {}
    for o in rs.AllObjects():
        lay = rs.ObjectLayer(o)
        layer_objs.setdefault(lay, []).append(o)
        parent = rs.ObjectParentObject(o)
        if parent:
            defn = rs.BlockInstanceName(parent, True)
            block_defs.setdefault(defn, []).append(o)
        part_objs[rs.ObjectName(o) or ""] = o

    for a in assignments:
        mat = mats[(a["finish"]["id"], a.get("scale_multiplier", 1.0))]
        if a["target_kind"] == "layer":
            assign_to_objects(layer_objs.get(a["target_name"], []), mat)
        elif a["target_kind"] == "part":
            o = part_objs.get(a["target_name"])
            if o:
                assign_to_objects([o], mat)
        else:  # block definition: scripted BlockEdit — assign on definition geometry
            objs = block_defs.get(a["target_name"], [])
            if objs:
                rs.EnableRedraw(False)
                rs.Command(f'-_BlockEdit "{a["target_name"]}" _Enter', False)
                inner = [o for o in rs.AllObjects() if rs.IsBlockInstance(o) is False
                         and rs.ObjectLayer(o) in rs.BlockLayers(a["target_name"]) or True]
                assign_to_objects(rs.AllObjects(), mat)  # definition is the active space
                rs.Command('-_BlockEditSave _Enter', False)
                rs.EnableRedraw(True)

    # camera + render
    rs.Command("-_Zoom _Extents _Enter", False)
    if CAMERA == "front":
        rs.Command("-_View _Front _Enter", False)
    elif CAMERA == "top":
        rs.Command("-_View _Top _Enter", False)
    else:
        rs.Command("-_View _Perspective _Enter -_Zoom _Extents _Enter", False)

    out = os.path.join(OUT_DIR, "render.png")
    samples = {"draft": 32, "standard": 128, "high": 512}[QUALITY]
    # V-Ray is the current renderer on the worker machine; -_Render writes the frame.
    # TODO(vray-py): use the V-Ray Python API for sample counts / progressive cutoff:
    #   import vray ... app.renderer.set("samples", samples)
    rs.Command(f'-_RenderResolution {WIDTH} {HEIGHT} _Enter', False)
    rs.Command(f'-_Render _Enter -_SaveRenderWindowAs "{out}" _Enter -_CloseRenderWindow', False)
    if not os.path.exists(out):
        rs.RenderMeshPreview  # placeholder to keep linters quiet
        raise RuntimeError("render output missing")
    print("RENDER_OK", out)


main()
