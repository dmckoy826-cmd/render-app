# -*- coding: utf-8 -*-
"""Apply safely identified Rhino materials and request a synchronous V-Ray render.

Supports single renders and Batch SKU Layer x Finish Queue renders, with per-target
scale multiplier, 0-90 degree grain rotation, and U/V seam offsets in inches.
"""
from __future__ import division
import json
import math
import os
import shutil
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
CAMERA_POSE = os.environ.get("FF_CAMERA_POSE", "")
NAMED_VIEW = os.environ.get("FF_NAMED_VIEW", "")
KEEP_FILE_VIEW = os.environ.get("FF_KEEP_FILE_VIEW", "") == "1"
USE_FILE_VRAY = os.environ.get("FF_USE_FILE_VRAY", "") == "1"
VRAY_DEVICE = os.environ.get("FF_VRAY_DEVICE", "")
VRAY_SPEED = os.environ.get("FF_VRAY_SPEED", "")
ISOLATE_SKU = os.environ.get("FF_ISOLATE_SKU", "")
BATCH_FILE = os.environ.get("FF_BATCH", "")
JOB_ID = os.environ.get("FF_JOB_ID", "")
API = os.environ.get("FF_API", "http://localhost:8000").rstrip("/")


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


def report_progress(pct, stage):
    if not JOB_ID:
        return
    try:
        req = System.Net.WebRequest.Create("%s/api/agent/jobs/%s/progress" % (API, JOB_ID))
        req.Method = "POST"
        req.ContentType = "application/json"
        req.Timeout = 5000
        body = System.Text.Encoding.UTF8.GetBytes(json.dumps({"progress": int(pct), "stage": str(stage)}))
        req.ContentLength = body.Length
        stream = req.GetRequestStream()
        stream.Write(body, 0, body.Length)
        stream.Close()
        resp = req.GetResponse()
        resp.Close()
    except Exception:
        pass


def sanitize_filename(name):
    leaf = str(name or "render").split("::")[-1].strip()
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if c in bad or ord(c) < 32 else c for c in leaf).strip(" .")
    return cleaned or "unnamed"


def current_renderer():
    current = rs.DefaultRenderer()
    name = str(current)
    if "vray" not in name.lower().replace("-", "").replace(" ", ""):
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
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    roots = [
        os.environ.get("FF_VRAY_SCRIPTS", ""),
        os.path.join(program_files, "Chaos", "V-Ray", "V-Ray for Rhinoceros"),
        os.path.join(program_files, "Chaos Group", "V-Ray", "V-Ray for Rhinoceros"),
    ]
    for base in (os.path.join(program_files, "Chaos"), os.path.join(program_files, "Chaos Group")):
        if os.path.isdir(base):
            for dirpath, _dirnames, filenames in os.walk(base):
                if "rh8VRay.py" in filenames or "rhVRay.py" in filenames:
                    roots.append(dirpath)
    for root in roots:
        if root and os.path.isdir(root) and root not in sys.path:
            sys.path.append(root)
    for mod_name in ("rh8VRay", "rhVRay") if sys.version_info[0] >= 3 else ("rhVRay", "rh8VRay"):
        try:
            return __import__(mod_name)
        except ImportError:
            continue
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
    render_mat = None
    try:
        render_mat = Rhino.Render.RenderMaterial.CreateBasicMaterial(sc.doc.Materials[index], sc.doc)
        if render_mat is not None:
            sc.doc.RenderMaterials.Add(render_mat)
    except Exception:
        render_mat = None
    return {"index": index, "render_material": render_mat, "name": material.Name}


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


def _transform_mapping_plane(base_plane, rotation_deg, u_off_units, v_off_units):
    plane = Rhino.Geometry.Plane(base_plane)
    if abs(rotation_deg) > 1e-7:
        plane.Rotate(math.radians(rotation_deg), plane.ZAxis, plane.Origin)
    if abs(u_off_units) > 1e-7 or abs(v_off_units) > 1e-7:
        plane.Origin = plane.Origin + (plane.XAxis * u_off_units) + (plane.YAxis * v_off_units)
    return plane


def mapping_for(obj, sw_w, sw_h, rotation_deg=0.0, offset_u_in=0.0, offset_v_in=0.0, relaxed=False):
    inches_per_unit = Rhino.RhinoMath.UnitScale(sc.doc.ModelUnitSystem, Rhino.UnitSystem.Inches)
    if inches_per_unit <= 0:
        if relaxed:
            inches_per_unit = 1.0
        else:
            raise RuntimeError("Unknown model units; cannot establish real-world texture size.")
    w, h = sw_w / inches_per_unit, sw_h / inches_per_unit
    u_off = float(offset_u_in or 0.0) / inches_per_unit
    v_off = float(offset_v_in or 0.0) / inches_per_unit
    rot = float(rotation_deg or 0.0)
    interval = Rhino.Geometry.Interval
    plane = planar_mapping(obj.Geometry)
    if plane is not None:
        t_plane = _transform_mapping_plane(plane, rot, u_off, v_off)
        mapping = Rhino.Render.TextureMapping.CreatePlaneMapping(
            t_plane, interval(0, w), interval(0, h), interval(0, max(w, h)))
    elif relaxed or abs(sw_w - sw_h) <= max(sw_w, sw_h) * 1e-7:
        t_plane = _transform_mapping_plane(Rhino.Geometry.Plane.WorldXY, rot, u_off, v_off)
        mapping = Rhino.Render.TextureMapping.CreateBoxMapping(
            t_plane, interval(0, w), interval(0, h), interval(0, max(w, h)), True)
    else:
        raise RuntimeError("Rectangular swatches on multi-face objects cannot yet be mapped "
                           "at a verified physical scale. Use a planar surface or a square swatch.")
    if mapping is None:
        raise RuntimeError("Rhino could not create the real-world texture mapping.")
    return mapping


def _eval_mapping(mapping, point, vector):
    try:
        res = mapping.Evaluate(point, vector)
        if isinstance(res, tuple) and len(res) == 2:
            return res
    except TypeError:
        pass
    pt = clr.StrongBox[Rhino.Geometry.Point3d](Rhino.Geometry.Point3d.Origin)
    rc = mapping.Evaluate(point, vector, pt)
    return rc, pt.Value


def verify_object_mapping(obj, expected):
    box = clr.StrongBox[Rhino.Geometry.Transform](Rhino.Geometry.Transform.Identity)
    try:
        actual = obj.GetTextureMapping(1, box)
        xform = box.Value
    except TypeError:
        actual = obj.GetTextureMapping(1)
        xform = Rhino.Geometry.Transform.Identity
    if actual is None or (xform is not None and not xform.IsIdentity):
        raise RuntimeError("Rhino returned a missing or transformed texture mapping; scale cannot be verified.")
    if actual.MappingType != expected.MappingType:
        raise RuntimeError("Rhino retained a different texture projection than requested.")
    if actual.DataCRC(0) == expected.DataCRC(0):
        return
    points = [(0.0, 0.0, 0.0), (0.37, 1.9, -2.4), (5.1, -3.3, 7.2)]
    normals = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    try:
        for xyz in points:
            for normal in normals:
                point = Rhino.Geometry.Point3d(*xyz)
                vector = Rhino.Geometry.Vector3d(*normal)
                before = _eval_mapping(expected, point, vector)
                after = _eval_mapping(actual, point, vector)
                if before[0] != after[0]:
                    raise ValueError("mapping projection differs")
                for axis in ("X", "Y", "Z"):
                    a, b = getattr(before[1], axis), getattr(after[1], axis)
                    if abs(a - b) > 1e-7 * max(1.0, abs(a), abs(b)):
                        raise ValueError("mapping coordinates differ")
    except Exception:
        raise RuntimeError("Rhino could not verify the requested texture mapping and scale.")


def _has_assigned_material(obj, mat_info):
    if obj is None:
        return False
    src_ok = (obj.Attributes.MaterialSource == Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject or
              str(obj.Attributes.MaterialSource) == "MaterialFromObject")
    if not src_ok:
        return False
    idx = mat_info["index"] if isinstance(mat_info, dict) else mat_info
    if obj.Attributes.MaterialIndex == idx or obj.Attributes.MaterialIndex >= 0:
        return True
    if getattr(obj, "RenderMaterial", None) is not None or getattr(obj.Attributes, "RenderMaterial", None) is not None:
        return True
    return False


def assign_object(oid, mat_info, assignment):
    obj = sc.doc.Objects.FindId(oid)
    if obj is None or rs.IsObjectLocked(oid):
        raise RuntimeError("A target object is missing or locked; no render was produced.")
    f = assignment["finish"]
    mult = float(assignment.get("scale_multiplier", 1))
    rot = float(assignment.get("rotation_deg", 0.0) or 0.0)
    off_u = float(assignment.get("offset_u_in", 0.0) or 0.0)
    off_v = float(assignment.get("offset_v_in", 0.0) or 0.0)
    mapping = mapping_for(obj, float(f["swatch_width_in"]) * mult,
                          float(f["swatch_height_in"]) * mult,
                          rotation_deg=rot, offset_u_in=off_u, offset_v_in=off_v)
    material_index = mat_info["index"] if isinstance(mat_info, dict) else mat_info
    render_mat = mat_info.get("render_material") if isinstance(mat_info, dict) else None
    attr = obj.Attributes.Duplicate()
    attr.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
    attr.MaterialIndex = material_index
    if render_mat is not None:
        try:
            attr.RenderMaterial = render_mat
        except Exception:
            pass
    if not sc.doc.Objects.ModifyAttributes(obj, attr, True):
        obj.Attributes.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
        obj.Attributes.MaterialIndex = material_index
        if render_mat is not None:
            try:
                obj.Attributes.RenderMaterial = render_mat
            except Exception:
                pass
        obj.CommitChanges()
    obj = sc.doc.Objects.FindId(oid)
    if not _has_assigned_material(obj, mat_info):
        raise RuntimeError(
            "Rhino did not retain the requested object material (source=%s, index=%s, expected=%s, render_mat=%s)." % (
                getattr(obj.Attributes, "MaterialSource", None) if obj else None,
                getattr(obj.Attributes, "MaterialIndex", None) if obj else None,
                material_index,
                getattr(obj, "RenderMaterial", None) if obj else None,
            )
        )
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
        updated = definitions_by_name().get(definition.Name)
        verified = {}
        for obj in updated.GetObjects() or []:
            if isinstance(obj, Rhino.DocObjects.InstanceObject):
                continue
            info = identity(obj, definition.Name)
            if info and info["key"] in wanted:
                if not _has_assigned_material(obj, materials[info["key"]]):
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


def build_batch_target_index(need_parts=False):
    """Index layers, top-level objects, and block objects once before the batch loop."""
    layer_full_by_idx = {}
    layer_short_by_idx = {}
    for layer in sc.doc.Layers:
        if layer.IsDeleted:
            continue
        layer_full_by_idx[layer.Index] = layer.FullPath or layer.Name or ""
        layer_short_by_idx[layer.Index] = layer.Name or ""

    objs_by_layer_idx = {}
    objs_by_block = {}
    objs_by_part = {}
    top_RenderObjs = []

    enum_settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    enum_settings.NormalObjects = True
    enum_settings.HiddenObjects = True
    enum_settings.LockedObjects = False
    for obj in sc.doc.Objects.GetObjectList(enum_settings) or []:
        if obj is None:
            continue
        top_RenderObjs.append(obj)
        if isinstance(obj, Rhino.DocObjects.InstanceObject):
            continue
        if obj.ObjectType == Rhino.DocObjects.ObjectType.Light:
            continue
        lidx = obj.Attributes.LayerIndex
        objs_by_layer_idx.setdefault(lidx, []).append(obj)
        if need_parts:
            info = identity(obj, None)
            if info and info.get("renderable"):
                objs_by_part.setdefault(info["key"], []).append(obj)
                if info.get("name"):
                    objs_by_part.setdefault(info["name"], []).append(obj)

    for d in sc.doc.InstanceDefinitions:
        if d.IsDeleted:
            continue
        b_list = objs_by_block.setdefault(d.Name, [])
        for obj in d.GetObjects() or []:
            if obj is None or isinstance(obj, Rhino.DocObjects.InstanceObject):
                continue
            if obj.ObjectType == Rhino.DocObjects.ObjectType.Light:
                continue
            b_list.append(obj)
            lidx = obj.Attributes.LayerIndex
            objs_by_layer_idx.setdefault(lidx, []).append(obj)
            if need_parts:
                info = identity(obj, d.Name)
                if info and info.get("renderable"):
                    objs_by_part.setdefault(info["key"], []).append(obj)
                    if info.get("name"):
                        objs_by_part.setdefault(info["name"], []).append(obj)

    return {
        "layer_full_by_idx": layer_full_by_idx,
        "layer_short_by_idx": layer_short_by_idx,
        "objs_by_layer_idx": objs_by_layer_idx,
        "objs_by_block": objs_by_block,
        "objs_by_part": objs_by_part,
        "top_objs": top_RenderObjs,
    }


def apply_target_finish(assignment, mat_info, mapped_ids, target_index=None):
    """Apply finish + scale + rotation + offset to a target (layer, block, or part) quickly."""
    target_kind = assignment.get("target_kind", "layer")
    target_name = assignment.get("target_name", "")
    if not target_name:
        return
    material_index = mat_info["index"] if isinstance(mat_info, dict) else mat_info
    render_mat = mat_info.get("render_material") if isinstance(mat_info, dict) else None
    f = assignment["finish"]
    mult = float(assignment.get("scale_multiplier", 1))
    rot = float(assignment.get("rotation_deg", 0.0) or 0.0)
    off_u = float(assignment.get("offset_u_in", 0.0) or 0.0)
    off_v = float(assignment.get("offset_v_in", 0.0) or 0.0)
    sw_w = float(f["swatch_width_in"]) * mult
    sw_h = float(f["swatch_height_in"]) * mult
    mapping_token = (round(sw_w, 4), round(sw_h, 4), round(rot, 4), round(off_u, 4), round(off_v, 4))

    if target_index is None:
        target_index = build_batch_target_index(need_parts=(target_kind == "part"))

    matched_objs = []
    if target_kind == "layer":
        for layer in sc.doc.Layers:
            if layer.IsDeleted:
                continue
            full = layer.FullPath or layer.Name or ""
            short = layer.Name or ""
            if full == target_name or short == target_name or full.endswith("::" + target_name):
                try:
                    if layer.RenderMaterialIndex != material_index:
                        layer.RenderMaterialIndex = material_index
                    if render_mat is not None:
                        layer.RenderMaterial = render_mat
                    sc.doc.Layers.Modify(layer, layer.Index, False)
                except Exception:
                    pass
                matched_objs.extend(target_index["objs_by_layer_idx"].get(layer.Index, []))
    elif target_kind == "block":
        matched_objs.extend(target_index["objs_by_block"].get(target_name, []))
    elif target_kind == "part":
        matched_objs.extend(target_index["objs_by_part"].get(target_name, []))

    for obj in matched_objs:
        try:
            # Always fetch the live RhinoObject by Id for top-level objects so we never
            # overwrite current visibility (IsHidden) with a stale Attributes snapshot.
            live_obj = sc.doc.Objects.FindId(obj.Id) or obj
            cur_src = live_obj.Attributes.MaterialSource
            cur_idx = live_obj.Attributes.MaterialIndex
            if (cur_src != Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject or
                    cur_idx != material_index):
                attr = live_obj.Attributes.Duplicate()
                attr.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
                attr.MaterialIndex = material_index
                if render_mat is not None:
                    try:
                        attr.RenderMaterial = render_mat
                    except Exception:
                        pass
                if not sc.doc.Objects.ModifyAttributes(live_obj, attr, True):
                    live_obj.Attributes.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
                    live_obj.Attributes.MaterialIndex = material_index
                    if render_mat is not None:
                        try:
                            live_obj.Attributes.RenderMaterial = render_mat
                        except Exception:
                            pass
                    live_obj.CommitChanges()
        except Exception:
            pass
        oid_key = str(obj.Id)
        if mapped_ids.get(oid_key) != mapping_token:
            try:
                live_obj = sc.doc.Objects.FindId(obj.Id) or obj
                mapping = mapping_for(live_obj, sw_w, sw_h, rotation_deg=rot,
                                      offset_u_in=off_u, offset_v_in=off_v, relaxed=True)
                if mapping is not None:
                    sc.doc.Objects.ModifyTextureMapping(live_obj.Id, 1, mapping)
                    mapped_ids[oid_key] = mapping_token
            except Exception:
                pass


def isolate_sku_layer(target_sku, all_sku_layers, target_index=None):
    """Turn ON only target_sku (and its ancestor/child layers) and turn OFF all other SKU layers."""
    other_skus = set(all_sku_layers) - set([target_sku])

    def is_same_or_child(layer_path, short_name, sku_name):
        return (layer_path == sku_name or
                short_name == sku_name or
                layer_path.startswith(sku_name + "::") or
                layer_path.endswith("::" + sku_name))

    def is_ancestor(layer_path, sku_name):
        return sku_name.startswith(layer_path + "::")

    all_layers = [l for l in sc.doc.Layers if not l.IsDeleted]
    layer_by_id = {l.Id: l for l in all_layers}

    def ancestor_indices_of(layer):
        out = set()
        pid = getattr(layer, "ParentLayerId", System.Guid.Empty)
        while pid and pid != System.Guid.Empty and pid in layer_by_id:
            parent = layer_by_id[pid]
            out.add(parent.Index)
            pid = getattr(parent, "ParentLayerId", System.Guid.Empty)
        return out

    other_seed_indices = set()
    target_seed_indices = set()
    first_target_idx = None

    for layer in all_layers:
        full = layer.FullPath or layer.Name or ""
        short = layer.Name or ""
        if is_same_or_child(full, short, target_sku):
            target_seed_indices.add(layer.Index)
            if first_target_idx is None:
                first_target_idx = layer.Index
        elif any(is_same_or_child(full, short, o) for o in other_skus):
            other_seed_indices.add(layer.Index)

    # Expand descendants (any layer whose ancestor is in target_seed or other_seed)
    target_indices = set(target_seed_indices)
    other_indices = set(other_seed_indices)
    for layer in all_layers:
        anc = ancestor_indices_of(layer)
        if anc & target_seed_indices:
            target_indices.add(layer.Index)
        elif anc & other_seed_indices:
            other_indices.add(layer.Index)

    # Also include ancestors of target_sku so target_sku can be visible in Rhino
    for layer in list(all_layers):
        if layer.Index in target_indices:
            target_indices |= ancestor_indices_of(layer)

    other_indices -= target_indices

    def get_all_doc_objects():
        enum_settings = Rhino.DocObjects.ObjectEnumeratorSettings()
        enum_settings.NormalObjects = True
        enum_settings.HiddenObjects = True
        enum_settings.LockedObjects = True
        try:
            enum_settings.VisibleFilter = False
        except Exception:
            pass
        objs = list(sc.doc.Objects.GetObjectList(enum_settings) or [])
        if not objs:
            for oid in rs.AllObjects(select=False, include_lights=False, include_grips=False) or []:
                o = sc.doc.Objects.FindId(oid)
                if o is not None:
                    objs.append(o)
        return objs

    rs.EnableRedraw(False)
    try:
        # 1. Turn ON target_indices from top-level parent down to child layers first
        target_sorted = sorted(
            [l for l in all_layers if l.Index in target_indices],
            key=lambda l: (l.FullPath or l.Name or "").count("::"),
        )
        for layer in target_sorted:
            full = layer.FullPath or layer.Name or ""
            try:
                if hasattr(sc.doc.Layers, "ForceLayerVisible"):
                    sc.doc.Layers.ForceLayerVisible(layer.Id)
            except Exception:
                pass
            try:
                layer.IsVisible = True
                if hasattr(layer, "SetPersistentVisibility"):
                    layer.SetPersistentVisibility(True)
                sc.doc.Layers.Modify(layer, layer.Index, True)
            except Exception:
                pass
            try:
                rs.LayerVisible(full, True)
            except Exception:
                pass

        # 2. Ensure Rhino's CurrentLayerIndex is NEVER one of other_indices
        if first_target_idx is not None:
            try:
                sc.doc.Layers.SetCurrentLayerIndex(first_target_idx, True)
            except Exception:
                pass
        if sc.doc.Layers.CurrentLayerIndex in other_indices:
            for layer in all_layers:
                if layer.Index not in other_indices:
                    try:
                        layer.IsVisible = True
                        sc.doc.Layers.Modify(layer, layer.Index, True)
                        if sc.doc.Layers.SetCurrentLayerIndex(layer.Index, True):
                            break
                    except Exception:
                        pass

        # 3. Explicitly Show objects on target_indices and Hide objects on other_indices
        # BEFORE turning off other_indices layers (and with VisibleFilter=False) so Rhino's
        # object enumerator never skips objects on hidden layers.
        fresh_top_objs = get_all_doc_objects()
        hidden_cnt = 0
        shown_cnt = 0
        for obj in fresh_top_objs:
            if obj is None or obj.ObjectType == Rhino.DocObjects.ObjectType.Light:
                continue
            lidx = obj.Attributes.LayerIndex
            if lidx in target_indices:
                sc.doc.Objects.Show(obj.Id, True)
                shown_cnt += 1
            elif lidx in other_indices:
                sc.doc.Objects.Hide(obj.Id, True)
                hidden_cnt += 1

        # 4. Unconditionally turn OFF all other SKU layers (children first, then parents)
        other_sorted = sorted(
            [l for l in all_layers if l.Index in other_indices],
            key=lambda l: (l.FullPath or l.Name or "").count("::"),
            reverse=True,
        )
        for layer in other_sorted:
            full = layer.FullPath or layer.Name or ""
            try:
                layer.IsVisible = False
                if hasattr(layer, "SetPersistentVisibility"):
                    layer.SetPersistentVisibility(False)
                sc.doc.Layers.Modify(layer, layer.Index, True)
            except Exception:
                pass
            try:
                rs.LayerVisible(full, False)
            except Exception:
                pass

        print(
            "ISOLATE_SKU target=%s target_layers=%d other_sku_layers=%d shown_objs=%d hidden_objs=%d"
            % (target_sku, len(target_indices), len(other_indices), shown_cnt, hidden_cnt)
        )
    finally:
        rs.EnableRedraw(True)
    sc.doc.Views.Redraw()


def configure_vray_acceleration(vray):
    """Configure V-Ray GPU/RTX engine and noise/time limits via the V-Ray Scene API."""
    if not hasattr(vray, "Scene"):
        return

    def set_plugin_prop(plugin_path, key, val):
        try:
            node = vray.Scene[plugin_path]
            if node is None:
                return
            try:
                setattr(node, key, val)
            except Exception:
                node[key] = val
        except Exception:
            pass

    if VRAY_DEVICE and VRAY_DEVICE != "file":
        # V-Ray for Rhino engine constants: 0=CPU, 5=CUDA (GPU), 7=RTX
        engine_map = {"cpu": 0, "cuda": 5, "rtx": 7}
        eng = engine_map.get(VRAY_DEVICE.lower())
        if eng is not None:
            try:
                if hasattr(vray, "SetRenderEngine"):
                    vray.SetRenderEngine(eng)
            except Exception:
                pass
            try:
                if hasattr(vray, "RenderEngine"):
                    vray.RenderEngine = eng
            except Exception:
                pass
            set_plugin_prop("/SettingsRTEngine", "opencl_texsize", 2048)
            if VRAY_DEVICE.lower() == "rtx":
                set_plugin_prop("/SettingsRTEngine", "gpu_bundle_size", 128)
                set_plugin_prop("/SettingsRTEngine", "enable_raytracing", 1)

    if VRAY_SPEED and VRAY_SPEED != "file":
        # Presets: (noise_threshold, max_time_minutes, max_subdivs)
        speed_map = {
            "turbo": (0.05, 0.25, 8),      # ~15s max, noise 0.05
            "fast": (0.025, 0.75, 12),     # ~45s max, noise 0.025
            "balanced": (0.015, 1.5, 16),  # ~90s max, noise 0.015
            "high": (0.008, 3.0, 24),      # ~180s max, noise 0.008
        }
        preset = speed_map.get(VRAY_SPEED.lower())
        if preset:
            noise, max_mins, max_subdivs = preset
            set_plugin_prop("/SettingsImageSampler", "type", 3)  # Progressive
            set_plugin_prop("/SettingsImageSampler", "progressive_threshold", noise)
            set_plugin_prop("/SettingsImageSampler", "progressive_maxTime", max_mins)
            set_plugin_prop("/SettingsImageSampler", "progressive_maxSubdivs", max_subdivs)
            set_plugin_prop("/SettingsImageSampler", "dmc_threshold", noise)
            set_plugin_prop("/SettingsDMCGI", "adaptive_amount", 0.85)
            set_plugin_prop("/SettingsRTEngine", "noise_threshold", noise)
            set_plugin_prop("/SettingsRTEngine", "max_render_time", max_mins)
            set_plugin_prop("/SettingsRTEngine", "max_sample_level", max_subdivs * 50)


def configure_camera_and_output(vray, out_dir, out_filename):
    active_view = sc.doc.Views.ActiveView
    if active_view is None:
        views = sc.doc.Views.GetViewList(True, False)
        active_view = views[0] if views else None
    if active_view is None:
        raise RuntimeError("Could not find an active Rhino viewport for rendering.")
    sc.doc.Views.ActiveView = active_view
    vp = active_view.ActiveViewport
    applied_custom_view = False
    if NAMED_VIEW:
        try:
            nv_idx = sc.doc.NamedViews.FindByName(NAMED_VIEW)
            if nv_idx >= 0 and sc.doc.NamedViews.Restore(nv_idx, vp):
                applied_custom_view = True
            else:
                raise RuntimeError("Named view '%s' was not found in the Rhino document." % NAMED_VIEW)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("Could not restore Rhino named view '%s': %s" % (NAMED_VIEW, exc))
    elif CAMERA_POSE:
        try:
            pose = json.loads(CAMERA_POSE)
            inches_per_unit = Rhino.RhinoMath.UnitScale(sc.doc.ModelUnitSystem, Rhino.UnitSystem.Inches)
            scale_to_doc = (1.0 / inches_per_unit) if inches_per_unit > 0 else 1.0
            eye = [float(v) * scale_to_doc for v in pose["eye"]]
            target = [float(v) * scale_to_doc for v in pose["target"]]
            up = [float(v) for v in pose.get("up", [0.0, 0.0, 1.0])]
            vp.SetProjection(Rhino.Display.DefinedViewportProjection.Perspective, "Perspective", False)
            vp.SetCameraLocations(
                Rhino.Geometry.Point3d(target[0], target[1], target[2]),
                Rhino.Geometry.Point3d(eye[0], eye[1], eye[2]),
            )
            vp.CameraUp = Rhino.Geometry.Vector3d(up[0], up[1], up[2])
            applied_custom_view = True
        except Exception as exc:
            raise RuntimeError("Could not apply custom 3D viewer camera: %s" % exc)
    elif KEEP_FILE_VIEW:
        applied_custom_view = True
    if not applied_custom_view:
        proj_map = {
            "front": (Rhino.Display.DefinedViewportProjection.Front, "Front"),
            "top": (Rhino.Display.DefinedViewportProjection.Top, "Top"),
        }
        proj, view_name = proj_map.get(CAMERA, (Rhino.Display.DefinedViewportProjection.Perspective, "Perspective"))
        vp.SetProjection(proj, view_name, True)
        vp.ZoomExtents()
    active_view.Redraw()

    if not USE_FILE_VRAY:
        settings = sc.doc.RenderSettings
        settings.UseViewportSize = False
        settings.ImageSize = System.Drawing.Size(WIDTH, HEIGHT)
        sc.doc.RenderSettings = settings
    try:
        if not USE_FILE_VRAY and hasattr(vray, "SetRenderOutputSize"):
            vray.SetRenderOutputSize(WIDTH, HEIGHT)
        scene_out = vray.Scene["/SettingsOutput"] if hasattr(vray, "Scene") else None
        if scene_out is not None:
            props = [("img_dir", out_dir), ("img_file", out_filename), ("save_image", True)]
            if not USE_FILE_VRAY:
                props = [("img_width", WIDTH), ("img_height", HEIGHT),
                         ("rgn_width", WIDTH), ("rgn_height", HEIGHT)] + props
            for k, val in props:
                try:
                    setattr(scene_out, k, val)
                except Exception:
                    try:
                        scene_out[k] = val
                    except Exception:
                        pass
    except Exception:
        pass


def run_batch(batch_cfg, renderer, vray, structure=None):
    output_dir = os.path.abspath(batch_cfg.get("output_dir") or OUT_DIR)
    sku_layers = batch_cfg.get("sku_layers") or []
    struct_skus = [s["name"] for s in (structure or {}).get("sku_layers", []) if s.get("name")]
    # Also detect any layer in the live Rhino doc that holds top-level block instances
    doc_instance_layers = []
    try:
        enum_s = Rhino.DocObjects.ObjectEnumeratorSettings()
        enum_s.NormalObjects = True
        enum_s.HiddenObjects = True
        enum_s.LockedObjects = True
        for obj in sc.doc.Objects.GetObjectList(enum_s) or []:
            if isinstance(obj, Rhino.DocObjects.InstanceObject):
                lyr = sc.doc.Layers[obj.Attributes.LayerIndex]
                if lyr and not lyr.IsDeleted:
                    lname = lyr.FullPath or lyr.Name or ""
                    if lname:
                        doc_instance_layers.append(lname)
    except Exception:
        pass
    all_sku_layers = list(
        set(batch_cfg.get("all_sku_layers") or [])
        | set(sku_layers)
        | set(struct_skus)
        | set(doc_instance_layers)
    )
    base_assignments = batch_cfg.get("base_assignments") or []
    variations = batch_cfg.get("variations") or []
    if not sku_layers:
        raise RuntimeError("Batch render requires at least one SKU layer.")
    if not variations:
        raise RuntimeError("Batch render requires at least one finish variation in the queue.")
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    mats_by_token = {}
    mapped_ids = {}

    def get_mat(assignment):
        f = assignment.get("finish") or {}
        if f.get("id") is None:
            raise RuntimeError("Batch assignment is missing finish details.")
        token = (f["id"], float(assignment.get("scale_multiplier", 1)))
        if token not in mats_by_token:
            mats_by_token[token] = make_material(assignment)
        return mats_by_token[token]

    for a in base_assignments:
        if a.get("finish"):
            get_mat(a)
    for var in variations:
        for ov in var.get("overrides") or []:
            if ov.get("finish"):
                get_mat(ov)

    need_parts = any(
        a.get("target_kind") == "part"
        for a in base_assignments
    ) or any(
        ov.get("target_kind") == "part"
        for var in variations
        for ov in (var.get("overrides") or [])
    )
    target_index = build_batch_target_index(need_parts=need_parts)
    configure_vray_acceleration(vray)

    rs.EnableRedraw(False)
    try:
        for a in base_assignments:
            if a.get("finish") and a.get("target_name"):
                apply_target_finish(a, get_mat(a), mapped_ids, target_index=target_index)
    finally:
        rs.EnableRedraw(True)

    total_renders = len(sku_layers) * len(variations)
    done_count = 0
    saved_files = []
    last_png = None

    for sku_i, sku_layer in enumerate(sku_layers):
        isolate_sku_layer(sku_layer, all_sku_layers, target_index=target_index)
        sku_folder_name = sanitize_filename(sku_layer)
        sku_dir = os.path.join(output_dir, sku_folder_name)
        if not os.path.isdir(sku_dir):
            os.makedirs(sku_dir)

        for var_i, var in enumerate(variations):
            pct = 10 + int(80.0 * done_count / max(1, total_renders))
            label = var.get("label") or ("Render_%d" % (var_i + 1))
            report_progress(
                pct,
                "SKU %d/%d (%s) - Finish %d/%d (%s)" % (
                    sku_i + 1, len(sku_layers), sku_folder_name,
                    var_i + 1, len(variations), label,
                ),
            )
            override_keys = set((ov.get("target_kind", "layer"), ov.get("target_name")) for ov in (var.get("overrides") or []))
            rs.EnableRedraw(False)
            try:
                for a in base_assignments:
                    if (a.get("target_kind", "layer"), a.get("target_name")) not in override_keys:
                        if a.get("finish") and a.get("target_name"):
                            apply_target_finish(a, get_mat(a), mapped_ids, target_index=target_index)
                for ov in var.get("overrides") or []:
                    if ov.get("finish") and ov.get("target_name"):
                        apply_target_finish(ov, get_mat(ov), mapped_ids, target_index=target_index)
            finally:
                rs.EnableRedraw(True)

            # Re-verify SKU isolation right after finish assignments before rendering
            isolate_sku_layer(sku_layer, all_sku_layers, target_index=target_index)

            png_name = sanitize_filename(label) + ".png"
            dest_png = os.path.join(sku_dir, png_name)
            temp_png_name = "batch_frame_%d_%d.png" % (sku_i, var_i)
            temp_png = os.path.join(OUT_DIR, temp_png_name)
            if os.path.exists(temp_png):
                os.remove(temp_png)
            # Always let V-Ray write into temporary OUT_DIR so V-Ray's Frame Buffer
            # never holds a Windows directory lock on the user's output folder.
            configure_camera_and_output(vray, OUT_DIR, temp_png_name)
            vray.Render(0, 0, -1)
            if not os.path.isfile(temp_png) or os.path.getsize(temp_png) == 0:
                rs.Command('-_SaveRenderWindowAs "%s" _Enter' % temp_png, False)
            if not os.path.isfile(temp_png) or os.path.getsize(temp_png) == 0:
                raise RuntimeError("V-Ray did not save %s for SKU '%s'." % (png_name, sku_layer))
            if os.path.exists(dest_png):
                try:
                    os.remove(dest_png)
                except Exception:
                    pass
            shutil.copyfile(temp_png, dest_png)
            saved_files.append(dest_png)
            last_png = temp_png
            done_count += 1

    out = os.path.join(OUT_DIR, "render.png")
    shutil.copyfile(last_png, out)
    image = System.Drawing.Image.FromFile(out)
    try:
        actual_w, actual_h = image.Width, image.Height
    finally:
        image.Dispose()
    manifest = {
        "protocol": 1,
        "engine": "V-Ray",
        "renderer": renderer,
        "image": "render.png",
        "width": actual_w,
        "height": actual_h,
        "quality": "current V-Ray settings",
        "batch": True,
        "output_dir": output_dir,
        "saved_files": saved_files,
    }
    with open(os.path.join(OUT_DIR, "manifest.json"), "w") as fh:
        json.dump(manifest, fh)
    print("BATCH_RENDER_OK %d files in %s" % (len(saved_files), output_dir))


def main():
    if QUALITY != "current":
        raise RuntimeError("V-Ray quality presets are not integrated yet. Use current V-Ray settings.")
    with open(STRUCTURE) as fh:
        structure = json.load(fh)
    if structure.get("target_schema") != SCHEMA:
        raise RuntimeError("This model needs a fresh analysis by the updated Rhino worker before rendering.")
    rs.EnableRedraw(False)
    ok = open_or_import_model(MODEL)
    rs.EnableRedraw(True)
    if ok is False:
        raise RuntimeError("Rhino could not open/import %s." % MODEL)
    if BATCH_FILE and os.path.isfile(BATCH_FILE):
        with open(BATCH_FILE) as bfh:
            batch_cfg = json.load(bfh)
        renderer = ensure_vray()
        vray = vray_wrapper()
        run_batch(batch_cfg, renderer, vray, structure=structure)
        return
    if not rs.AllObjects():
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

    if ISOLATE_SKU:
        sku_names = [s["name"] for s in structure.get("sku_layers", []) if "name" in s]
        if not sku_names:
            sku_names = [l["name"] for l in structure.get("layers", []) if "name" in l]
        isolate_sku_layer(ISOLATE_SKU, sku_names)

    out = os.path.join(OUT_DIR, "render.png")
    if os.path.exists(out):
        os.remove(out)
    configure_vray_acceleration(vray)
    configure_camera_and_output(vray, OUT_DIR, "render.png")
    vray.Render(0, 0, -1)
    if not os.path.isfile(out) or os.path.getsize(out) == 0:
        rs.Command('-_SaveRenderWindowAs "%s" _Enter' % out, False)
    if not os.path.isfile(out) or os.path.getsize(out) == 0:
        raise RuntimeError("V-Ray did not save a render image; no viewport fallback is used.")
    image = System.Drawing.Image.FromFile(out)
    try:
        actual_w, actual_h = image.Width, image.Height
        if not USE_FILE_VRAY and (actual_w != WIDTH or actual_h != HEIGHT):
            raise RuntimeError("V-Ray returned %dx%d, expected %dx%d." %
                               (actual_w, actual_h, WIDTH, HEIGHT))
    finally:
        image.Dispose()
    manifest = {"protocol": 1, "engine": "V-Ray", "renderer": renderer,
                "image": "render.png", "width": actual_w, "height": actual_h,
                "quality": "current V-Ray settings",
                "use_file_vray_settings": USE_FILE_VRAY}
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
    try:
        Rhino.RhinoApp.Exit()
    except Exception:
        pass
