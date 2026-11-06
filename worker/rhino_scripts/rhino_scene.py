"""RhinoCommon adapter for FinishFlow's scene/assignment contract.

Definition geometry is identified in its local coordinates; each occurrence is
transformed into model space for the browser preview. Import-time document GUIDs
are never used as persistent finish targets.
"""
from __future__ import division

import math
import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc

from ff_common import SceneBuilder, part_key

MAX_DEPTH = 32
MAX_PARTS = 250000
MAX_OCCURRENCES = 1000000


def layer_of(obj):
    layer = sc.doc.Layers[obj.Attributes.LayerIndex]
    color = layer.Color
    return layer.FullPath or layer.Name or "0", "#%02x%02x%02x" % (color.R, color.G, color.B)


def geometry_kind(geometry):
    g = Rhino.Geometry
    if isinstance(geometry, g.Mesh):
        return "mesh", True
    if isinstance(geometry, g.Brep):
        return "brep", True
    if isinstance(geometry, g.Extrusion):
        return "extrusion", True
    if isinstance(geometry, g.Surface):
        return "surface", True
    if hasattr(g, "SubD") and isinstance(geometry, g.SubD):
        return "subd", True
    if isinstance(geometry, g.Curve):
        return "curve", False
    return None, False


def box_values(box, factor=1.0):
    if box is None or not box.IsValid:
        raise ValueError("Rhino returned invalid geometry bounds.")
    return {"min": [box.Min.X * factor, box.Min.Y * factor, box.Min.Z * factor],
            "max": [box.Max.X * factor, box.Max.Y * factor, box.Max.Z * factor]}


def geometry_fingerprint(geometry, kind):
    if hasattr(geometry, "crc"):
        return geometry.DataCRC(0)
    try:
        if kind == "brep" and hasattr(geometry, "Faces"):
            return "%d:%d:%d:%d" % (
                geometry.Faces.Count,
                geometry.Edges.Count,
                geometry.Vertices.Count,
                1 if geometry.IsSolid else 0,
            )
        if kind == "mesh" and hasattr(geometry.Vertices, "Count"):
            return "%d:%d" % (geometry.Vertices.Count, geometry.Faces.Count)
        if kind == "extrusion" and hasattr(geometry, "ProfileCount"):
            return "%d:%d" % (geometry.ProfileCount, 1 if geometry.IsSolid else 0)
        if kind == "curve" and hasattr(geometry, "Degree"):
            return "%d:%d:%.4f" % (
                geometry.Degree,
                1 if geometry.IsClosed else 0,
                float(geometry.GetLength()),
            )
    except Exception:
        pass
    return geometry.DataCRC(0)


def identity(obj, owner):
    geometry = obj.Geometry
    kind, renderable = geometry_kind(geometry)
    if kind is None:
        return None
    layer, color = layer_of(obj)
    local_bbox = box_values(geometry.GetBoundingBox(True))
    # Geometry fingerprint does not depend on per-import RhinoObject IDs or
    # non-deterministic DWG/ACIS Brep DataCRC across Rhino processes.
    crc = geometry_fingerprint(geometry, kind)
    name = obj.Attributes.Name or ""
    key = part_key(owner, layer, kind, crc, local_bbox, name)
    display = name or "%s %s" % (layer, "linework" if kind == "curve" else kind)
    return {"key": key, "name": display, "layer": layer, "color": color,
            "kind": kind, "renderable": renderable}


def has_scaling(xform):
    # Rotation, translation and reflection preserve tile size. Non-unit scale,
    # nonuniform scale and shear do not. Fail closed rather than render wrong size.
    cols = [(xform.M00, xform.M10, xform.M20),
            (xform.M01, xform.M11, xform.M21),
            (xform.M02, xform.M12, xform.M22)]
    for col in cols:
        if abs(sum(v * v for v in col) - 1.0) > 1e-6:
            return True
    for i in range(3):
        for j in range(i + 1, 3):
            if abs(sum(cols[i][k] * cols[j][k] for k in range(3))) > 1e-6:
                return True
    return False


def preview_geometry(geometry, kind, factor):
    positions, triangles, lines = [], [], []
    if kind == "curve":
        result = geometry.TryGetPolyline()
        polyline = result[1] if result and result[0] else None
        if polyline is None:
            approximation = geometry.ToPolyline(sc.doc.ModelAbsoluteTolerance,
                                                 sc.doc.ModelAngleToleranceRadians, 0.0, 0.0)
            if approximation is not None:
                result = approximation.TryGetPolyline()
                polyline = result[1] if result and result[0] else None
        if polyline is not None:
            for p in polyline:
                positions.extend([p.X * factor, p.Y * factor, p.Z * factor])
            for i in range(len(positions) // 3 - 1):
                lines.extend([i, i + 1])
        return positions, triangles, lines
    meshes = []
    if kind == "mesh":
        meshes = [geometry]
    else:
        brep = geometry if kind == "brep" else geometry.ToBrep()
        if brep is not None:
            meshes = Rhino.Geometry.Mesh.CreateFromBrep(brep, Rhino.Geometry.MeshingParameters.Default) or []
    for mesh in meshes:
        start = len(positions) // 3
        for vertex in mesh.Vertices:
            positions.extend([vertex.X * factor, vertex.Y * factor, vertex.Z * factor])
        for face in mesh.Faces:
            triangles.extend([start + face.A, start + face.B, start + face.C])
            if face.IsQuad:
                triangles.extend([start + face.A, start + face.C, start + face.D])
    return positions, triangles, lines


def scan_document(include_geometry=True):
    builder = SceneBuilder(include_geometry)
    if str(sc.doc.ModelUnitSystem).lower() in ("none", "unset", "customunits"):
        raise ValueError("The drawing has no supported model units. Set units in Rhino first.")
    factor = Rhino.RhinoMath.UnitScale(sc.doc.ModelUnitSystem, Rhino.UnitSystem.Inches)
    if not factor or factor <= 0:
        raise ValueError("The drawing has no valid model units. Set its units in Rhino first.")

    def visit(obj, transform, ancestors, stack, sku_layer=None, sku_color="#8d929a"):
        if (len(builder.occurrences) + len(builder.unsupported) >= MAX_OCCURRENCES or
                len(builder.parts) >= MAX_PARTS):
            raise ValueError("Model has too many geometry objects for safe analysis.")
        if isinstance(obj, Rhino.DocObjects.InstanceObject):
            definition = obj.InstanceDefinition
            if definition is None:
                raise ValueError("A block instance has a missing definition.")
            name = definition.Name
            if len(stack) >= MAX_DEPTH or name in stack:
                raise ValueError("Block nesting is cyclic or too deep: %s" % name)
            if not ancestors and hasattr(obj, "Attributes") and obj.Attributes is not None:
                try:
                    sku_layer, sku_color = layer_of(obj)
                    builder.add_sku_layer(sku_layer, sku_color, block_name=name)
                except Exception:
                    pass
            builder.add_block(name)
            child_transform = transform * obj.InstanceXform
            for child in definition.GetObjects() or []:
                visit(child, child_transform, ancestors + [name], stack + [name], sku_layer, sku_color)
            return
        owner = ancestors[-1] if ancestors else None
        info = identity(obj, owner)
        if info is None:
            layer, _ = layer_of(obj)
            try:
                kind = str(obj.Geometry.GetType().Name)
            except Exception:
                kind = str(type(obj.Geometry))
            builder.add_unsupported(layer, ancestors, kind)
            return
        if not ancestors and hasattr(obj, "Attributes") and obj.Attributes is not None:
            sku_layer, sku_color = info["layer"], info["color"]
            builder.add_sku_layer(sku_layer, sku_color, block_name="")
        if sku_layer:
            builder.add_sku_layer(sku_layer, sku_color, part_layer=info["layer"])
        geometry = obj.Geometry.Duplicate()
        if geometry is None or not geometry.Transform(transform):
            raise ValueError("Could not transform geometry in '%s'." % info["name"])
        bbox = box_values(geometry.GetBoundingBox(True), factor)
        positions, triangles, lines = [], [], []
        if include_geometry:
            try:
                positions, triangles, lines = preview_geometry(geometry, info["kind"], factor)
            except Exception:
                builder.warn("Some Rhino geometry could not be tessellated for the preview.")
        builder.add_leaf(info["key"], info["name"], info["layer"], info["color"], owner,
                         ancestors, bbox, info["renderable"], obj.Id,
                         scaled=has_scaling(transform), positions=positions,
                         triangles=triangles, lines=lines, sku_layer=sku_layer)

    top_objects = []
    if hasattr(Rhino.DocObjects, "ObjectEnumeratorSettings") and hasattr(sc.doc.Objects, "GetObjectList"):
        try:
            enum_settings = Rhino.DocObjects.ObjectEnumeratorSettings()
            enum_settings.NormalObjects = True
            enum_settings.HiddenObjects = True
            enum_settings.LockedObjects = True
            enum_settings.ReferenceObjects = True
            enum_settings.ActiveObjects = True
            top_objects = list(sc.doc.Objects.GetObjectList(enum_settings) or [])
        except Exception:
            top_objects = []
    if not top_objects:
        ids = rs.AllObjects() or []
        for oid in ids:
            obj = sc.doc.Objects.FindId(oid)
            if obj is not None:
                top_objects.append(obj)
    # Divide the preview geometry budget across top-level SKU layers so an early
    # dense SKU cannot consume the entire interactive preview payload.
    top_layer_names = set()
    for obj in top_objects:
        if obj is not None:
            try:
                top_layer_names.add(layer_of(obj)[0])
            except Exception:
                pass
    builder.set_preview_sku_count(len(top_layer_names))
    for obj in top_objects:
        if obj is not None:
            visit(obj, Rhino.Geometry.Transform.Identity, [], [])
    return builder
