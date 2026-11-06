"""Rhino-independent checks for the worker's finish texture mapping policy."""
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "worker" / "rhino_scripts" / "render_model.py"


class Interval:
    def __init__(self, start, end):
        self.T0, self.T1 = start, end


class Plane:
    def __init__(self, other=None):
        self.Origin = (0, 0, 0)
        self.XAxis = self.YAxis = self.ZAxis = object()

    def Rotate(self, *_args):
        pass


Plane.WorldXY = Plane()


class RenderMappingPolicyTests(unittest.TestCase):
    def load_render_module(self):
        calls = []

        class TextureMapping:
            @staticmethod
            def CreateBoxMapping(plane, x, y, z, capped):
                mapping = types.SimpleNamespace(MappingType="Box")
                calls.append((plane, x, y, z, capped, mapping))
                return mapping

            @staticmethod
            def CreatePlaneMapping(*_args):
                raise AssertionError("finish mapping must always be Box")

        fake_rhino = types.SimpleNamespace(
            RhinoMath=types.SimpleNamespace(UnitScale=lambda _source, _target: 1.0),
            UnitSystem=types.SimpleNamespace(Inches="Inches"),
            Geometry=types.SimpleNamespace(Interval=Interval, Plane=Plane),
            Render=types.SimpleNamespace(
                TextureMapping=TextureMapping,
                TextureMappingType=types.SimpleNamespace(Box="Box")),
        )
        modules = {
            "Rhino": fake_rhino,
            "System": types.ModuleType("System"),
            "clr": types.ModuleType("clr"),
            "rhinoscriptsyntax": types.ModuleType("rhinoscriptsyntax"),
            "scriptcontext": types.SimpleNamespace(doc=types.SimpleNamespace(ModelUnitSystem="Inches")),
        }
        sys.path.insert(0, str(ROOT / "worker" / "rhino_scripts"))
        env = {"FF_MODEL": "model.3dm", "FF_ASSIGNMENTS": "assignments.json",
               "FF_STRUCTURE": "structure.json", "FF_OUT_DIR": "out",
               "FF_TEX_DIR": "textures", "FF_ERROR": "error.txt"}
        with patch.dict(sys.modules, modules), patch.dict(os.environ, env):
            spec = importlib.util.spec_from_file_location("render_model_mapping_test", SCRIPT)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module, calls

    def test_rectangular_finish_uses_box_mapping_for_every_target_geometry(self):
        render_model, calls = self.load_render_module()
        # The mapping policy must not change for planar versus multi-face geometry,
        # or when the caller is not using the relaxed batch-render path.
        for geometry in (object(), object()):
            mapping = render_model.mapping_for(
                types.SimpleNamespace(Geometry=geometry), 18.0, 36.0, relaxed=False)
            self.assertEqual(mapping.MappingType, "Box")
        self.assertEqual(len(calls), 2)
        for _plane, x, y, z, capped, mapping in calls:
            self.assertEqual((x.T0, x.T1), (0, 18.0))
            self.assertEqual((y.T0, y.T1), (0, 36.0))
            self.assertEqual((z.T0, z.T1), (0, 36.0))
            self.assertTrue(capped)
            self.assertEqual(mapping.MappingType, "Box")

    def test_mapping_dimensions_include_finish_scale_before_preview_or_render(self):
        render_model, calls = self.load_render_module()
        # These dimensions are the swatch dimensions after the assignment's scale
        # multiplier, which mapping_for turns into the object's Box mapping.
        mapping = render_model.mapping_for(types.SimpleNamespace(Geometry=object()), 24.0, 48.0)
        self.assertEqual(mapping.MappingType, "Box")
        _plane, x, y, z, _capped, _mapping = calls[0]
        self.assertEqual((x.T1, y.T1, z.T1), (24.0, 48.0, 48.0))


if __name__ == "__main__":
    unittest.main()
