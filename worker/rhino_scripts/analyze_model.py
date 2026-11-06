"""Import with Rhino and export structure plus a tessellated model-space preview.

FF_MODEL, FF_OUT_JSON, FF_OUT_GEOMETRY and optional FF_OUT_PNG are provided by the
Windows worker. Actual Rhino operation is validated on the user's Windows machine.
"""
from __future__ import division
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import Rhino
import System
import rhinoscriptsyntax as rs
import scriptcontext as sc
from rhino_scene import scan_document

MODEL = os.environ["FF_MODEL"]
OUT_JSON = os.environ["FF_OUT_JSON"]
OUT_GEOMETRY = os.environ["FF_OUT_GEOMETRY"]
OUT_GEOMETRY_LAYERS = os.environ.get("FF_OUT_GEOMETRY_LAYERS", "")
OUT_PNG = os.environ.get("FF_OUT_PNG", "")


def open_or_import_model(path):
    if path.lower().endswith(".3dm"):
        try:
            sc.doc.Modified = False
        except Exception:
            pass
        ok = rs.Command('-_Open "%s" _Enter' % path, False)
        if ok is False:
            ok = rs.Command('-_Import "%s" _Enter' % path, False)
        return ok
    return rs.Command('-_Import "%s" _Enter' % path, False)


def main():
    rs.EnableRedraw(False)
    ok = open_or_import_model(MODEL)
    rs.EnableRedraw(True)
    if ok is False:
        raise RuntimeError("Rhino could not open/import: %s" % MODEL)
    scene = scan_document(include_geometry=True,
                          detailed_geometry_archive_path=OUT_GEOMETRY_LAYERS or None)
    structure = scene.structure(os.path.basename(MODEL))
    if OUT_GEOMETRY_LAYERS and not structure.get("preview_layer_geometry"):
        try:
            os.remove(OUT_GEOMETRY_LAYERS)
        except OSError:
            pass
    try:
        named_views = [v.Name for v in sc.doc.NamedViews if getattr(v, "Name", None)]
        if named_views:
            structure["named_views"] = named_views
    except Exception:
        pass
    with open(OUT_GEOMETRY, "w") as fh:
        json.dump(scene.geometry(), fh, separators=(",", ":"), allow_nan=False)
    # Structure is the success marker: write only after geometry was serialized.
    with open(OUT_JSON, "w") as fh:
        json.dump(structure, fh, allow_nan=False)
    if OUT_PNG:
        try:
            view = sc.doc.Views.ActiveView
            if view is not None:
                view.ActiveViewport.SetProjection(
                    Rhino.Display.DefinedViewportProjection.Perspective, "Perspective", True
                )
                view.ActiveViewport.ZoomExtents()
                view.Redraw()
                bitmap = view.CaptureToBitmap(System.Drawing.Size(1200, 900))
                if bitmap is not None:
                    bitmap.Save(OUT_PNG, System.Drawing.Imaging.ImageFormat.Png)
                    bitmap.Dispose()
        except Exception as exc:
            print("Preview capture failed (non-fatal): %r" % exc)
    print("ANALYZE_OK %d parts, %d blocks, %d layers" %
          (len(structure["parts"]), len(structure["blocks"]), len(structure["layers"])))


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
finally:
    try:
        sc.doc.Modified = False
    except Exception:
        pass
    try:
        Rhino.RhinoApp.Exit()
    except Exception:
        pass
