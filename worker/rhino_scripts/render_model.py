"""Apply safely identified Rhino materials and request a synchronous V-Ray render.

This automation has not yet been verified in the user's Rhino/V-Ray installation.
It intentionally fails instead of substituting a viewport image, applying to
unknown BlockEdit objects, or reporting an unverified image as a render.
"""
from __future__ import division
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import Rhino
import System
import clr
import rhinoscriptsyntax as rs
import scriptcontext as sc
from ff_common import SCHEMA, match_editable_copies, plan_assignments, topology_signature
from rhino_scene import identity, scan_document

MODEL = os.environ["FF_MODEL"]
ASSIGN = os.environ["FF_ASSIGNMENTS"]
STRUCTURE = os.environ["FF_STRUCTURE"]
OUT_DIR = os.environ["FF_OUT_DIR"]
TEX_DIR = os.environ["FF_TEX_DIR"]
ERROR = os.environ["FF_ERROR"]
WIDTH = int(os.environ.get("FF_WIDTH", "1920"))
HEIGHT = int(os.environ.get("FF_HEIGHT", "1080"))
QUALITY = os.environ.get("FF_QUALITY", "current")
CAMERA = os.environ.get("FF_CAMERA", "iso")
API = os.environ.get("FF_API", "http://localhost:8000").rstrip("/")


def current_renderer():
    current = rs.DefaultRenderer()
    name = str(current)
    if "vray" not in name.lower().replace("-", "").replace(" ", ""):
        # Some RhinoScriptSyntax releases return a GUID, others a name.
        try:
            name = str(Rhino.PlugIns.PlugIn.GetInstalledPlugIns()[current])
        except Exception:
            pass
    return name


def ensure_vray():
    name = current_renderer()
    if "vray" not in name.lower().replace("-", "").replace(" ", ""):
        try:
            rs.DefaultRenderer("V-Ray for Rhino")
            name = current_renderer()
        except Exception:
            pass
    if "vray" not in name.lower().replace("-", "").replace(" ", ""):
        raise RuntimeError("V-Ray for Rhino is not the current renderer (found %s). "
                           "Enable it in Rhino and retry." % name)
    return name


def vray_wrapper():
    # Chaos documents these wrappers under its V-Ray for Rhinoceros installation.
    roots = [os.environ.get("FF_VRAY_SCRIPTS", ""),
             os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                          "Chaos", "V-Ray", "V-Ray for Rhinoceros")]
    for root in roots:
        if root and os.path.isdir(root) and root not in sys.path:
            sys.path.append(root)
    try:
        if sys.version_info[0] >= 3:
            import rh8VRay as wrapper
        else:
            import rhVRay as wrapper
        return wrapper
    except ImportError:
        raise RuntimeError("V-Ray's Rhino Python wrapper could not be loaded. Set FF_VRAY_SCRIPTS "
                           "to the folder containing rhVRay.py/rh8VRay.py.")


def make_material(assignment):
    finish = assignment["finish"]
    url = finish.get("file_url", "")
    if not url.startswith("/media/"):
        raise RuntimeError("Finish image URL is missing or invalid.")
    local = os.path.join(TEX_DIR, "finish_%s%s" % (finish["id"], os.path.splitext(url)[1]))
    if not os.path.exists(local):
        client = System.Net.WebClient()
        try:
            client.DownloadFile(API + url, local)
        finally:
            client.Dispose()
    material = Rhino.DocObjects.Material()
    material.Name = "FinishFlow_%s" % finish.get("name", finish["id"])
    if not material.SetBitmapTexture(local):
        raise RuntimeError("Rhino could not create the bitmap texture for %s." % material.Name)
    index = sc.doc.Materials.Add(material)
    texture = sc.doc.Materials[index].GetBitmapTexture() if index >= 0 else None
    if texture is None:
        raise RuntimeError("Rhino could not create material %s." % material.Name)
    if texture.MappingChannelId != 1 or texture.WcsProjected or texture.WcsBoxProjected:
        raise RuntimeError("The finish texture is not using object mapping channel 1; "
                           "the requested physical scale cannot be verified.")
    return index


def planar_mapping(geometry):
    try:
        if isinstance(geometry, Rhino.Geometry.Brep):
            if geometry.Faces.Count != 1:
                return None
            result = geometry.Faces[0].TryGetPlane()
        elif isinstance(geometry, Rhino.Geometry.Surface):
            result = geometry.TryGetPlane()
        else:
            return None
        return result[1] if result and result[0] else None
    except Exception:
        return None


def mapping_for(obj, sw_w, sw_h):
    inches_per_unit = Rhino.RhinoMath.UnitScale(sc.doc.ModelUnitSystem, Rhino.UnitSystem.Inches)
    if inches_per_unit <= 0:
        raise RuntimeError("Unknown model units; cannot establish real-world texture size.")
    w, h = sw_w / inches_per_unit, sw_h / inches_per_unit
    interval = Rhino.Geometry.Interval
    plane = planar_mapping(obj.Geometry)
    if plane is not None:
        mapping = Rhino.Render.TextureMapping.CreatePlaneMapping(
            plane, interval(0, w), interval(0, h), interval(0, max(w, h)))
    elif abs(sw_w - sw_h) <= max(sw_w, sw_h) * 1e-7:
        # A single box mapping preserves the same square tile on each box face.
        mapping = Rhino.Render.TextureMapping.CreateBoxMapping(
            Rhino.Geometry.Plane.WorldXY, interval(0, w), interval(0, w), interval(0, w), True)
    else:
        raise RuntimeError("Rectangular swatches on multi-face objects cannot yet be mapped "
                           "at a verified physical scale. Use a planar surface or a square swatch.")
    if mapping is None:
        raise RuntimeError("Rhino could not create the real-world texture mapping.")
    return mapping


def verify_object_mapping(obj, expected):
    # A mapping channel also carries an object transform; a non-identity transform
    # can change physical tile size even when the mapping itself looks correct.
    box = clr.StrongBox[Rhino.Geometry.Transform]()
    actual = obj.GetTextureMapping(1, box)
    if actual is None or not box.Value.IsIdentity:
        raise RuntimeError("Rhino returned a missing or transformed texture mapping; scale cannot be verified.")
    if actual.MappingType != expected.MappingType:
        raise RuntimeError("Rhino retained a different texture projection than requested.")
    if actual.DataCRC(0) == expected.DataCRC(0):
        return
    # Some Rhino versions attach different table metadata to identical mappings.
    # Compare evaluated coordinates instead of relying only on the table CRC.
    points = [(0.0, 0.0, 0.0), (0.37, 1.9, -2.4), (5.1, -3.3, 7.2)]
    normals = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    try:
        for xyz in points:
            for normal in normals:
                point = Rhino.Geometry.Point3d(*xyz)
                vector = Rhino.Geometry.Vector3d(*normal)
                before = expected.Evaluate(point, vector)
                after = actual.Evaluate(point, vector)
                if before[0] != after[0]:
                    raise ValueError("mapping projection differs")
                for axis in ("X", "Y", "Z"):
                    a, b = getattr(before[1], axis), getattr(after[1], axis)
                    if abs(a - b) > 1e-7 * max(1.0, abs(a), abs(b)):
                        raise ValueError("mapping coordinates differ")
    except Exception:
        raise RuntimeError("Rhino could not verify the requested texture mapping and scale.")


def assign_object(oid, material_index, assignment):
    obj = sc.doc.Objects.FindId(oid)
    if obj is None or rs.IsObjectLocked(oid):
        raise RuntimeError("A target object is missing or locked; no render was produced.")
    f = assignment["finish"]
    mult = float(assignment.get("scale_multiplier", 1))
    mapping = mapping_for(obj, float(f["swatch_width_in"]) * mult,
                          float(f["swatch_height_in"]) * mult)
    rs.ObjectMaterialSource(oid, 1)
    rs.ObjectMaterialIndex(oid, material_index)
    if rs.ObjectMaterialSource(oid) != 1 or rs.ObjectMaterialIndex(oid) != material_index:
        raise RuntimeError("Rhino did not retain the requested object material.")
    if not sc.doc.Objects.ModifyTextureMapping(oid, 1, mapping):
        raise RuntimeError("Rhino could not apply the requested texture mapping.")
    obj = sc.doc.Objects.FindId(oid)
    if obj is None:
        raise RuntimeError("Rhino could not find the object after applying its mapping.")
    verify_object_mapping(obj, mapping)
    return mapping


def definitions_by_name():
    return {d.Name: d for d in sc.doc.InstanceDefinitions if not d.IsDeleted}


def edit_definition(definition, wanted, materials):
    """Open a temporary identity instance and match only new editable copies.

    BlockEdit changes IDs; local geometry fingerprints and exact occurrence counts
    must match the original definition before we modify anything.
    """
    if definition.IsLinkedType or definition.IsReference or definition.IsTenuous:
        raise RuntimeError("Linked or reference block '%s' cannot be edited safely; embed it first." % definition.Name)
    expected = {}
    for obj in definition.GetObjects() or []:
        if obj.IsHidden or obj.IsLocked:
            raise RuntimeError("Block '%s' contains hidden or locked objects; unlock/show them before editing." % definition.Name)
        if isinstance(obj, Rhino.DocObjects.InstanceObject):
            continue
        info = identity(obj, definition.Name)
        if info and info["key"] in wanted:
            expected[info["key"]] = expected.get(info["key"], 0) + 1
    if set(expected) != set(wanted):
        raise RuntimeError("Definition '%s' changed since analysis; re-analyze." % definition.Name)
    temp_id = sc.doc.Objects.AddInstanceObject(definition.Index, Rhino.Geometry.Transform.Identity)
    if temp_id == System.Guid.Empty:
        raise RuntimeError("Could not create a temporary instance of '%s'." % definition.Name)
    opened = False
    try:
        before = set(str(x) for x in (rs.AllObjects() or []))
        rs.UnselectAllObjects()
        if not rs.SelectObject(temp_id):
            raise RuntimeError("Could not select temporary block '%s'." % definition.Name)
        if rs.Command("-_BlockEdit _Open _Enter", False) is False:
            raise RuntimeError("Could not open BlockEdit for '%s'." % definition.Name)
        opened = True
        candidates = []
        for oid in rs.AllObjects() or []:
            if str(oid) in before or rs.IsObjectLocked(oid):
                continue
            obj = sc.doc.Objects.FindId(oid)
            if obj is None or isinstance(obj, Rhino.DocObjects.InstanceObject):
                continue
            info = identity(obj, definition.Name)
            if info:
                candidates.append({"id": oid, "key": info["key"], "locked": False})
        try:
            copies = match_editable_copies(before, candidates, expected)
        except ValueError as exc:
            raise RuntimeError("Could not safely identify BlockEdit copies in '%s': %s" %
                               (definition.Name, exc))
        mappings = {}
        for key, ids in copies.items():
            for oid in ids:
                mapping = assign_object(oid, materials[key], wanted[key])
                if key in mappings:
                    verify_object_mapping(sc.doc.Objects.FindId(oid), mappings[key])
                mappings[key] = mapping
        if rs.Command("-_BlockEdit _SaveAndClose _Enter", False) is False:
            raise RuntimeError("Rhino could not save BlockEdit for '%s'." % definition.Name)
        opened = False
        # Reacquire definition after save: Rhino can replace table objects.
        updated = definitions_by_name().get(definition.Name)
        verified = {}
        for obj in updated.GetObjects() or []:
            if isinstance(obj, Rhino.DocObjects.InstanceObject):
                continue
            info = identity(obj, definition.Name)
            if info and info["key"] in wanted:
                if (int(obj.Attributes.MaterialSource) != 1 or
                        obj.Attributes.MaterialIndex != materials[info["key"]]):
                    raise RuntimeError("Could not verify saved material in '%s'." % definition.Name)
                verify_object_mapping(obj, mappings[info["key"]])
                verified[info["key"]] = verified.get(info["key"], 0) + 1
        if verified != expected:
            raise RuntimeError("Could not verify all edited geometry in '%s'." % definition.Name)
    finally:
        if opened:
            rs.Command("-_BlockEdit _DiscardAndCancel _Enter", False)
        rs.UnselectAllObjects()
        if rs.IsObject(temp_id) and not rs.DeleteObject(temp_id):
            raise RuntimeError("Could not remove temporary block instance '%s'." % definition.Name)


def main():
    if QUALITY != "current":
        raise RuntimeError("V-Ray quality presets are not integrated yet. Use current V-Ray settings.")
    with open(STRUCTURE) as fh:
        structure = json.load(fh)
    if structure.get("target_schema") != SCHEMA:
        raise RuntimeError("This model needs a fresh analysis by the updated Rhino worker before rendering.")
    if rs.Command('-_Import "%s" _Enter' % MODEL, False) is False or not rs.AllObjects():
        raise RuntimeError("Rhino could not import %s." % MODEL)
    scene = scan_document(include_geometry=False)
    if set(p["id"] for p in structure.get("parts", [])) != set(scene.parts):
        raise RuntimeError("Rhino geometry differs from the analyzed model; re-analyze before rendering.")
    with open(ASSIGN) as fh:
        plan = plan_assignments(scene, json.load(fh))
    definitions = definitions_by_name()
    for occurrence in scene.occurrences:
        if occurrence["key"] in plan:
            for name in occurrence["ancestors"]:
                d = definitions.get(name)
                if d is None or d.IsLinkedType or d.IsReference or d.IsTenuous:
                    raise RuntimeError("Linked/reference block '%s' needs to be embedded before editing." % name)
    renderer = ensure_vray()
    vray = vray_wrapper()
    mats_by_finish, materials = {}, {}
    for key, assignment in plan.items():
        f = assignment["finish"]
        token = (f["id"], float(assignment.get("scale_multiplier", 1)))
        if token not in mats_by_finish:
            mats_by_finish[token] = make_material(assignment)
        materials[key] = mats_by_finish[token]
    groups = {}
    for key in plan:
        owner = scene.parts[key]["block"]
        groups.setdefault(owner, {})[key] = plan[key]
    if None in groups:
        counts = {}
        for oid in rs.AllObjects() or []:
            obj = sc.doc.Objects.FindId(oid)
            if obj is None or isinstance(obj, Rhino.DocObjects.InstanceObject):
                continue
            info = identity(obj, None)
            if info and info["key"] in groups[None]:
                assign_object(oid, materials[info["key"]], plan[info["key"]])
                counts[info["key"]] = counts.get(info["key"], 0) + 1
        for key in groups[None]:
            if counts.get(key, 0) != len(scene.parts[key]["source_ids"]):
                raise RuntimeError("Could not identify all objects for '%s'." % scene.parts[key]["name"])
    for owner, wanted in groups.items():
        if owner is not None:
            definition = definitions_by_name().get(owner)
            if definition is None:
                raise RuntimeError("Block '%s' disappeared during editing." % owner)
            edit_definition(definition, wanted, materials)
    if plan and topology_signature(scan_document(include_geometry=False)) != topology_signature(scene):
        raise RuntimeError("The geometry or block structure changed during material assignment; "
                           "the render was stopped to avoid a wrong result.")

    view = {"front": "_Front", "top": "_Top"}.get(CAMERA, "_Perspective")
    if rs.Command("-_SetCurrentView _World %s _Enter" % view, False) is False:
        raise RuntimeError("Could not set the requested camera.")
    rs.ZoomExtents()
    settings = sc.doc.RenderSettings
    settings.UseViewportSize = False
    settings.ImageSize = System.Drawing.Size(WIDTH, HEIGHT)
    sc.doc.RenderSettings = settings
    out = os.path.join(OUT_DIR, "render.png")
    if os.path.exists(out):
        os.remove(out)
    # Chaos documents timeout=-1 as a synchronous V-Ray production render.
    vray.Render(0, 0, -1)
    saved = rs.Command('-_SaveRenderWindowAs "%s" _Enter' % out, False)
    if saved is False or not os.path.isfile(out) or os.path.getsize(out) == 0:
        raise RuntimeError("V-Ray did not save a render image; no viewport fallback is used.")
    image = System.Drawing.Image.FromFile(out)
    try:
        if image.Width != WIDTH or image.Height != HEIGHT:
            raise RuntimeError("V-Ray returned %dx%d, expected %dx%d." %
                               (image.Width, image.Height, WIDTH, HEIGHT))
    finally:
        image.Dispose()
    manifest = {"protocol": 1, "engine": "V-Ray", "renderer": renderer,
                "image": "render.png", "width": WIDTH, "height": HEIGHT,
                "quality": "current V-Ray settings"}
    with open(os.path.join(OUT_DIR, "manifest.json"), "w") as fh:
        json.dump(manifest, fh)
    print("RENDER_OK %s" % out)


try:
    main()
except Exception:
    print("RENDER_FAIL")
    traceback.print_exc()
    try:
        with open(ERROR, "w") as fh:
            fh.write(traceback.format_exc())
    except Exception:
        pass
finally:
    try:
        sc.doc.Modified = False
    except Exception:
        pass
