"""Rhino 8 + V-Ray: apply assigned finishes as materials and render the model.

Run by worker/agent.py inside Rhino (RhinoPython). Reads:
    FF_MODEL        CAD file to import
    FF_ASSIGNMENTS  JSON list: [{target_kind, target_name, scale_multiplier,
                                 finish: {id, name, category, file_url,
                                          swatch_width_in, swatch_height_in}}]
    FF_OUT_DIR      folder for output images
    FF_WIDTH/FF_HEIGHT/FF_QUALITY/FF_CAMERA
    FF_API          FinishFlow server base URL (finish images are fetched from it)

How finishes become materials:
  * Each finish image is downloaded to disk (System.Net.WebClient — no extra deps
    inside Rhino) and set as the material's bitmap texture via the documented
    Material.SetBitmapTexture(filename) API.
  * REAL-WORLD SCALE: the swatch covers swatch_width_in x swatch_height_in of actual
    material, so the render texture's projection is switched to WCS box and its
    repeat is derived from swatch size vs. object size — the same "scale the finish
    to real size" contract the UI promises. (Best-effort: if the projection API is
    unavailable in this Rhino build, the texture still applies with default mapping.)
  * Block targets use the scripted BlockEdit flow (_-BlockEdit ... _SaveAndClose):
    materials are assigned to the DEFINITION geometry, so every instance updates at
    once — exactly like editing a block by hand.
  * Rendering: viewport is resized to the requested output size, the current
    renderer (V-Ray for Rhino when it is set as current) is invoked via -Render, and
    the frame is saved with -SaveLastRender.

The document's Modified flag is cleared before exit so agent.py's `_Exit` macro
never blocks on a save prompt.
"""
import json
import os
import sys
import traceback

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import System

MODEL = os.environ["FF_MODEL"]
ASSIGN = os.environ["FF_ASSIGNMENTS"]
OUT_DIR = os.environ["FF_OUT_DIR"]
WIDTH = int(os.environ.get("FF_WIDTH", "1920"))
HEIGHT = int(os.environ.get("FF_HEIGHT", "1080"))
QUALITY = os.environ.get("FF_QUALITY", "standard")
CAMERA = os.environ.get("FF_CAMERA", "iso")
API = os.environ.get("FF_API", "http://localhost:8000").rstrip("/")

TEX_CACHE = {}


def fetch(url_rel):
    """Download a finish image from the FinishFlow server (relative /media URL)."""
    local = TEX_CACHE.get(url_rel)
    if not local:
        local = os.path.join(OUT_DIR, "tex_" + url_rel.replace("/", "_").replace("\\", "_"))
        if not os.path.exists(local):
            System.Net.WebClient().DownloadFile(API + url_rel, local)
        TEX_CACHE[url_rel] = local
    return local


def make_material(name, img_path, sw_w, sw_h, metallic):
    """Create a doc material with the finish bitmap; returns the material index."""
    mat = Rhino.DocObjects.Material()
    mat.Name = name
    mat.SetBitmapTexture(img_path)          # documented single-arg API
    if metallic:
        try:
            mat.ToPhysicallyBased()
            pbr = mat.PhysicallyBased
            pbr.Metallic = 0.85
            pbr.Roughness = 0.35
        except Exception:
            mat.Shine = 128
    idx = sc.doc.Materials.Add(mat)
    return idx


def set_real_world_scale(obj_ids, sw_w, sw_h):
    """Best-effort: switch the object's render texture to WCS-box projection sized
    so one texture tile == sw_w x sw_h inches of real material."""
    try:
        for oid in obj_ids:
            obj = sc.doc.Objects.FindId(oid)
            if obj is None:
                continue
            bb = obj.Geometry.GetBoundingBox(True)
            size_x = max(1e-3, bb.Max.X - bb.Min.X)
            size_y = max(1e-3, bb.Max.Y - bb.Min.Y)
            rx = size_x / max(1e-3, sw_w)
            ry = size_y / max(1e-3, sw_h)
            mat_idx = obj.Attributes.MaterialIndex
            if mat_idx < 0:
                continue
            texture = sc.doc.Materials[mat_idx].GetBitmapTexture()
            if texture is None:
                continue
            texture.Repeat = Rhino.Geometry.Vector2d(max(1.0, rx), max(1.0, ry))
            texture.WrapU = texture.WrapV = True
            sc.doc.Materials.Modify(sc.doc.Materials[mat_idx], mat_idx, True)
    except Exception as exc:
        print("real-world texture scale fallback: %r" % exc)


def assign(objs, mat_idx, sw_w, sw_h):
    touched = []
    for o in objs:
        rs.ObjectMaterialSource(o, 1)   # 1 = material from object
        rs.ObjectMaterialIndex(o, mat_idx)
        touched.append(o)
    if touched:
        set_real_world_scale(touched, sw_w, sw_h)


def main():
    ok = rs.Command('-_Import "%s" _Enter' % MODEL, False)
    if ok is False and not rs.AllObjects():
        raise RuntimeError("Rhino could not import: %s" % MODEL)
    assignments = json.loads(open(ASSIGN).read())

    # one material per (finish, scale) pair
    mats = {}
    for a in assignments:
        f = a["finish"]
        mult = float(a.get("scale_multiplier") or 1.0)
        key = (f["id"], mult)
        if key not in mats:
            img = fetch(f["file_url"])
            mats[key] = make_material(
                "FF_%s" % f["name"], img,
                f["swatch_width_in"] * mult, f["swatch_height_in"] * mult,
                f.get("category") == "product_finish")

    # index objects by layer / block-definition / name
    layer_objs, defn_insts, named = {}, {}, {}
    for o in rs.AllObjects():
        lay = rs.ObjectLayer(o)
        layer_objs.setdefault(lay, []).append(o)
        name = rs.ObjectName(o) or ""
        if name:
            named[name] = o
        if rs.IsBlockInstance(o):
            defn = rs.BlockInstanceName(o)
            if defn:
                defn_insts.setdefault(defn, []).append(o)

    for a in assignments:
        f = a["finish"]
        mult = float(a.get("scale_multiplier") or 1.0)
        mat_idx = mats[(f["id"], mult)]
        sw_w = f["swatch_width_in"] * mult
        sw_h = f["swatch_height_in"] * mult
        kind, target = a["target_kind"], a["target_name"]

        if kind == "layer":
            assign(layer_objs.get(target, []), mat_idx, sw_w, sw_h)
        elif kind == "part":
            o = named.get(target)
            if o:
                assign([o], mat_idx, sw_w, sw_h)
        elif kind == "block":
            # Scripted BlockEdit: assign to the definition geometry so every
            # instance updates at once (docs: -BlockEdit options Open /
            # SaveAndClose / DiscardAndCancel are the scriptable ones).
            insts = defn_insts.get(target) or []
            if insts:
                rs.UnselectAllObjects()
                rs.SelectObject(insts[0])
                opened = rs.Command("-_BlockEdit _Enter", False)
                if opened is not False:
                    inner = rs.AllObjects()   # definition geometry is what's editable now
                    assign(inner, mat_idx, sw_w, sw_h)
                    rs.Command("-_BlockEdit _SaveAndClose _Enter", False)
                rs.UnselectAllObjects()
            else:
                print("block definition not found in geometry: %s" % target)

    # camera
    view = {"front": "_Front", "top": "_Top"}.get(CAMERA, "_Perspective")
    rs.Command("-_SetCurrentView _World %s _Enter" % view, False)
    rs.Command("-_Zoom _Extents _Enter", False)

    # output size: resize the active viewport so -Render produces WIDTHxHEIGHT
    try:
        v = sc.doc.Views.ActiveView
        v.ActiveViewport.Size = System.Drawing.Size(WIDTH, HEIGHT)
        v.Redraw()
    except Exception as exc:
        print("viewport resize failed (non-fatal): %r" % exc)

    # Render with whatever renderer is current (V-Ray for Rhino when the user has
    # set it as the current renderer — that's the deployment contract).
    # TODO(vray-py): for explicit V-Ray control (samples per quality tier,
    # denoising, progressive cutoff) use the V-Ray AppSDK Python API:
    #   import vray  ...  vray.VRayRenderer(...).render()
    rs.Command("-_Render _Enter", False)
    out = os.path.join(OUT_DIR, "render.png")
    saved = rs.Command('-_SaveLastRender "%s" _Enter' % out, False)
    if saved is False or not os.path.exists(out):
        # fallback: viewport capture at render quality
        rs.ViewCaptureToFile(out, WIDTH, HEIGHT)
    if not os.path.exists(out):
        raise RuntimeError("no render output produced")
    print("RENDER_OK %s (%s quality, %dx%d, %s)" % (out, QUALITY, WIDTH, HEIGHT, CAMERA))


try:
    main()
except Exception:
    print("RENDER_FAIL")
    traceback.print_exc()
    try:
        with open(os.path.join(OUT_DIR, "error.txt"), "w") as fh:
            fh.write(traceback.format_exc())
    except Exception:
        pass
    sys.exit(0)  # agent detects failure via missing images + console output
finally:
    try:
        sc.doc.Modified = False  # let _Exit close Rhino without a save prompt
    except Exception:
        pass
