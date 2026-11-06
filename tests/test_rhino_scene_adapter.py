"""Exercise recursive Rhino adapter with deterministic stand-ins, not Rhino itself."""
import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker" / "rhino_scripts"))


class Point:
    def __init__(self, x, y, z): self.X, self.Y, self.Z = x, y, z


class BoundingBox:
    def __init__(self, points):
        self.IsValid = True
        self.Min = Point(*[min(getattr(p, axis) for p in points) for axis in ("X", "Y", "Z")])
        self.Max = Point(*[max(getattr(p, axis) for p in points) for axis in ("X", "Y", "Z")])


class Transform:
    def __init__(self, x=0, y=0, z=0, scale=1):
        self.x, self.y, self.z, self.scale = x, y, z, scale
        self.M00 = self.M11 = self.M22 = scale
        self.M10 = self.M20 = self.M01 = self.M21 = self.M02 = self.M12 = 0

    def __mul__(self, other):
        return Transform(self.x + self.scale * other.x, self.y + self.scale * other.y,
                         self.z + self.scale * other.z, self.scale * other.scale)


Transform.Identity = Transform()


class Face:
    A, B, C, D, IsQuad = 0, 1, 2, 2, False


class Mesh:
    def __init__(self, points, crc):
        self.Vertices = [Point(*p) for p in points]
        self.Faces = [Face()]
        self.crc = crc

    def Duplicate(self): return copy.deepcopy(self)
    def GetBoundingBox(self, _): return BoundingBox(self.Vertices)
    def DataCRC(self, _): return self.crc
    def Transform(self, transform):
        for p in self.Vertices:
            p.X = p.X * transform.scale + transform.x
            p.Y = p.Y * transform.scale + transform.y
            p.Z = p.Z * transform.scale + transform.z
        return True


class Brep: pass
class Extrusion: pass
class Surface: pass
class SubD: pass
class Curve: pass


class Layer:
    def __init__(self, name):
        self.FullPath = self.Name = name
        self.Color = types.SimpleNamespace(R=20, G=40, B=60)


class Obj:
    def __init__(self, oid, geometry, layer=0, name=""):
        self.Id, self.Geometry = oid, geometry
        self.Attributes = types.SimpleNamespace(LayerIndex=layer, Name=name)


class Definition:
    def __init__(self, name, children): self.Name, self.children = name, children
    def GetObjects(self): return self.children


class Instance:
    def __init__(self, oid, definition, transform, layer=1):
        self.Id, self.InstanceDefinition, self.InstanceXform = oid, definition, transform
        self.Attributes = types.SimpleNamespace(LayerIndex=layer)


class SceneAdapterTests(unittest.TestCase):
    def load_adapter(self, objects, layers=None):
        geometry = types.SimpleNamespace(Mesh=Mesh, Brep=Brep, Extrusion=Extrusion,
            Surface=Surface, SubD=SubD, Curve=Curve, Transform=Transform)
        rhino = types.SimpleNamespace(Geometry=geometry,
            DocObjects=types.SimpleNamespace(InstanceObject=Instance),
            RhinoMath=types.SimpleNamespace(UnitScale=lambda _a, _b: 0.5),
            UnitSystem=types.SimpleNamespace(Inches="inches"))
        doc = types.SimpleNamespace(ModelUnitSystem="test units", Layers=layers or [Layer("AFUWK-INNER"), Layer("ROOT")],
            Objects=types.SimpleNamespace(FindId=lambda oid: objects.get(oid)))
        modules = {"Rhino": rhino,
                   "rhinoscriptsyntax": types.SimpleNamespace(AllObjects=lambda: list(objects)),
                   "scriptcontext": types.SimpleNamespace(doc=doc)}
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location("rhino_scene_under_test", ROOT / "worker/rhino_scripts/rhino_scene.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        return mod

    def test_nested_transforms_layers_and_units(self):
        inner = Obj("def-mesh", Mesh([(0, 0, 0), (4, 0, 0), (0, 2, 0)], 73), name="panel")
        child_def = Definition("CHILD", [inner])
        parent_def = Definition("PARENT", [Instance("nested", child_def, Transform(y=3))])
        first = Instance("first", parent_def, Transform(x=10))
        second = Instance("second", parent_def, Transform(x=20))
        adapter = self.load_adapter({"first": first, "second": second})
        scene = adapter.scan_document()
        struct = scene.structure("nested.dwg")
        self.assertEqual([layer["name"] for layer in struct["layers"]], ["AFUWK-INNER"])
        self.assertEqual({b["name"]: b["instance_count"] for b in struct["blocks"]}, {"PARENT": 2, "CHILD": 2})
        part = struct["parts"][0]
        self.assertEqual(part["block"], "CHILD")
        self.assertEqual(part["block_paths"], [["PARENT", "CHILD"]])
        self.assertEqual(part["occurrence_count"], 2)
        self.assertEqual(part["sku_layers"], ["ROOT"])
        self.assertEqual(struct["sku_layers"][0]["name"], "ROOT")
        self.assertEqual(part["bbox"], {"min": [5, 1.5, 0], "max": [12, 2.5, 0]})
        preview = scene.geometry()["parts"][0]
        self.assertEqual(preview["sku_layer"], "ROOT")
        self.assertEqual(preview["positions"][:3], [5, 1.5, 0])
        self.assertEqual(preview["positions"][9:12], [10, 1.5, 0])
        self.assertEqual(preview["triangles"], [0, 1, 2, 3, 4, 5])

    def test_nested_layers_keep_exact_instance_and_definition_layer_identity(self):
        layers = [Layer("SKU-A::Panels"), Layer("SKU-B::Panels")]
        objects = {
            "a": Obj("a", Mesh([(0, 0, 0), (2, 0, 0), (0, 2, 0)], 99), layer=0),
            "b": Obj("b", Mesh([(0, 0, 0), (2, 0, 0), (0, 2, 0)], 99), layer=1),
        }
        scene = self.load_adapter(objects, layers=layers).scan_document()
        structure = scene.structure("sku.3dm")
        self.assertEqual({sku["name"] for sku in structure["sku_layers"]}, {"SKU-A::Panels", "SKU-B::Panels"})
        self.assertEqual({part["sku_layer"] for part in scene.geometry()["parts"]},
                         {"SKU-A::Panels", "SKU-B::Panels"})
        self.assertEqual({tuple(part["part_layers"]) for part in structure["sku_layers"]},
                         {("SKU-A::Panels",), ("SKU-B::Panels",)})

    def test_block_instance_layer_is_separate_from_definition_geometry_layer(self):
        layers = [Layer("Definition::Panels"), Layer("Default"),
                  Layer("SKU Group::SKU-A"), Layer("SKU Group::SKU-B")]
        definition = Definition("CABINET", [Obj("panel", Mesh([(0, 0, 0), (2, 0, 0), (0, 2, 0)], 81), layer=0)])
        objects = {
            "a": Instance("a", definition, Transform(x=10), layer=2),
            "b": Instance("b", definition, Transform(x=20), layer=3),
        }
        scene = self.load_adapter(objects, layers=layers).scan_document()
        geometry = scene.geometry()["parts"]
        self.assertEqual({part["sku_layer"] for part in geometry},
                         {"SKU Group::SKU-A", "SKU Group::SKU-B"})
        self.assertEqual({part["layer"] for part in geometry}, {"Definition::Panels"})
        self.assertEqual(len({part["id"] for part in geometry}), 1)

    def test_scaled_instance_is_reported_for_safe_planning(self):
        inner = Obj("one", Mesh([(0, 0, 0), (1, 0, 0), (0, 1, 0)], 18))
        inst = Instance("instance", Definition("BLOCK", [inner]), Transform(scale=2))
        scene = self.load_adapter({"instance": inst}).scan_document(include_geometry=False)
        self.assertTrue(scene.occurrences[0]["scaled"])

    def test_cycle_is_rejected(self):
        definition = Definition("LOOP", [])
        instance = Instance("instance", definition, Transform())
        definition.children.append(instance)
        with self.assertRaisesRegex(ValueError, "cyclic"):
            self.load_adapter({"instance": instance}).scan_document()


if __name__ == "__main__":
    unittest.main()
