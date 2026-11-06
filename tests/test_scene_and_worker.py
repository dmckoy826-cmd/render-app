"""Rhino-independent tests for targeting, conflict handling and worker output."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker" / "rhino_scripts"))
sys.path.insert(0, str(ROOT / "worker"))
import ff_common as common
import agent

BOX = {"min": [0, 0, 0], "max": [2, 2, 2]}


def assignment(kind, target, finish_id=1, scale=1):
    return {"target_kind": kind, "target_name": target, "scale_multiplier": scale,
            "finish": {"id": finish_id, "swatch_width_in": 12, "swatch_height_in": 12}}


def add_part(scene, key, owner, path, layer="INNER", source="geometry-1", renderable=True, scaled=False, sku_layer=None):
    scene.add_leaf(key, "panel", layer, "#123456", owner, path, BOX, renderable, source,
                   scaled=scaled, positions=[0, 0, 0, 2, 0, 0, 0, 2, 0], triangles=[0, 1, 2],
                   sku_layer=sku_layer)


def shared_scene(renderable=True, scaled=False):
    scene = common.SceneBuilder()
    scene.add_block("A"); scene.add_block("SHARED")
    add_part(scene, "part-1", "SHARED", ["A", "SHARED"], renderable=renderable, scaled=scaled)
    scene.add_block("B"); scene.add_block("SHARED")
    add_part(scene, "part-1", "SHARED", ["B", "SHARED"], renderable=renderable, scaled=scaled)
    return scene


class TargetingTests(unittest.TestCase):
    def test_stable_part_keys_distinguish_geometry_owner_and_layer(self):
        args = ("CASE", "AFUWK", "brep", 12345, BOX, "Door \u00e9")
        self.assertEqual(common.part_key(*args), common.part_key(*args))
        self.assertNotEqual(common.part_key(*args), common.part_key("CASE", "AFUWK", "brep", 12346, BOX, "Door \u00e9"))
        self.assertNotEqual(common.part_key(*args), common.part_key("OTHER", "AFUWK", "brep", 12345, BOX, "Door \u00e9"))
        self.assertNotEqual(common.part_key(*args), common.part_key("CASE", "OTHER", "brep", 12345, BOX, "Door \u00e9"))

    def test_nested_structure_and_geometry_indices_include_all_occurrences(self):
        scene = shared_scene()
        structure = scene.structure("file.dwg")
        part = structure["parts"][0]
        self.assertEqual(part["occurrence_count"], 2)
        self.assertEqual(part["matching_objects"], 1)
        self.assertEqual(part["block_paths"], [["A", "SHARED"], ["B", "SHARED"]])
        self.assertEqual({b["name"]: b["instance_count"] for b in structure["blocks"]},
                         {"A": 1, "B": 1, "SHARED": 2})
        self.assertEqual(scene.geometry()["parts"][0]["triangles"], [0, 1, 2, 3, 4, 5])

    def test_preview_geometry_is_partitioned_by_sku_layer(self):
        scene = common.SceneBuilder()
        scene.add_block("SHARED")
        scene.add_sku_layer("SKU-A", block_name="SHARED", part_layer="INNER")
        scene.add_sku_layer("SKU-B", block_name="SHARED", part_layer="INNER")
        add_part(scene, "same-part", "SHARED", ["SHARED"], source="a", sku_layer="SKU-A")
        add_part(scene, "same-part", "SHARED", ["SHARED"], source="b", sku_layer="SKU-B")

        structure = scene.structure("file.3dm")
        self.assertEqual(structure["preview_schema"], 2)
        self.assertEqual(structure["parts"][0]["sku_layers"], ["SKU-A", "SKU-B"])
        previews = scene.geometry()["parts"]
        self.assertEqual({p["sku_layer"] for p in previews}, {"SKU-A", "SKU-B"})
        self.assertEqual(len(previews), 2)

    def test_different_block_overrides_rejected_for_shared_definition(self):
        scene = shared_scene()
        with self.assertRaisesRegex(ValueError, "Conflicting finishes"):
            common.plan_assignments(scene, [assignment("block", "A", 1), assignment("block", "B", 2)])
        # Even an unassigned occurrence would be unintentionally changed.
        with self.assertRaisesRegex(ValueError, "Conflicting finishes"):
            common.plan_assignments(scene, [assignment("block", "A", 1)])

    def test_consistent_and_per_part_overrides(self):
        scene = shared_scene()
        plan = common.plan_assignments(scene, [assignment("block", "A", 1), assignment("block", "B", 1)])
        self.assertEqual(plan["part-1"]["finish"]["id"], 1)
        plan = common.plan_assignments(scene, [assignment("layer", "INNER", 3),
            assignment("block", "A", 1), assignment("block", "B", 2), assignment("part", "part-1", 4)])
        self.assertEqual(plan["part-1"]["finish"]["id"], 4)

    def test_assignment_to_empty_block_does_not_succeed_silently(self):
        scene = shared_scene()
        scene.add_block("EMPTY")
        with self.assertRaisesRegex(ValueError, "no supported geometry"):
            common.plan_assignments(scene, [assignment("block", "EMPTY")])

    def test_stale_target_invalid_scale_curve_and_scaled_instance_fail(self):
        with self.assertRaisesRegex(ValueError, "stale or missing"):
            common.plan_assignments(shared_scene(), [assignment("part", "old-name")])
        with self.assertRaisesRegex(ValueError, "finite"):
            common.plan_assignments(shared_scene(), [assignment("layer", "INNER", scale=float("nan"))])
        with self.assertRaisesRegex(ValueError, "linework"):
            common.plan_assignments(shared_scene(renderable=False), [assignment("layer", "INNER")])
        with self.assertRaisesRegex(ValueError, "scaled block"):
            common.plan_assignments(shared_scene(scaled=True), [assignment("layer", "INNER")])

    def test_preview_budget_is_shared_fairly_across_sku_layers(self):
        with mock.patch.object(common, "MAX_PREVIEW_VERTICES", 6):
            with mock.patch.object(common, "MAX_PREVIEW_INDICES", 6):
                scene = common.SceneBuilder()
                scene.set_preview_sku_count(2)
                scene.add_sku_layer("SKU-A", part_layer="INNER")
                scene.add_sku_layer("SKU-B", part_layer="INNER")
                add_part(scene, "p1", None, [], source="a", sku_layer="SKU-A")
                add_part(scene, "p2", None, [], source="b", sku_layer="SKU-B")
        self.assertEqual({part["sku_layer"] for part in scene.geometry()["parts"]}, {"SKU-A", "SKU-B"})
        self.assertEqual(scene.structure("a.3dm")["geometry_status"], "complete")

    def test_preview_budget_is_labeled_partial(self):
        with mock.patch.object(common, "MAX_PREVIEW_VERTICES", 2):
            scene = shared_scene()
        self.assertEqual(scene.structure("a.dwg")["geometry_status"], "partial")
        self.assertEqual(scene.geometry()["parts"], [])
        self.assertTrue(scene.structure("a.dwg")["geometry_warnings"])

    def test_layer_or_block_assignment_rejects_unhandled_geometry(self):
        scene = shared_scene()
        scene.add_unsupported("INNER", ["A", "SHARED"], "CustomSurface")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            common.plan_assignments(scene, [assignment("layer", "INNER")])
        with self.assertRaisesRegex(ValueError, "unsupported"):
            common.plan_assignments(scene, [assignment("block", "A")])
        # A specific supported part can still be selected without touching the unknown object.
        self.assertEqual(common.plan_assignments(scene, [assignment("part", "part-1")])["part-1"]["finish"]["id"], 1)

    def test_topology_comparison_detects_lost_or_moved_geometry(self):
        scene = shared_scene()
        baseline = common.topology_signature(scene)
        self.assertEqual(baseline, common.topology_signature(shared_scene()))
        scene.occurrences.pop()
        self.assertNotEqual(baseline, common.topology_signature(scene))
        scene = shared_scene()
        scene.occurrences[0]["bbox"] = {"min": [10, 0, 0], "max": [12, 2, 2]}
        self.assertNotEqual(baseline, common.topology_signature(scene))

    def test_block_edit_only_new_unlocked_matching_copies_are_selected(self):
        candidates = [
            {"id": "original", "key": "p1", "locked": False},
            {"id": "locked-copy", "key": "p1", "locked": True},
            {"id": "copy", "key": "p1", "locked": False},
            {"id": "unrelated", "key": "p2", "locked": False},
        ]
        self.assertEqual(common.match_editable_copies({"original"}, candidates, {"p1": 1}), {"p1": ["copy"]})
        with self.assertRaisesRegex(ValueError, "differ"):
            common.match_editable_copies({"original"}, candidates, {"p1": 2})


class WorkerOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        self.error = self.out / "error.txt"

    def manifest(self, engine="V-Ray", **extra):
        data = {"protocol": 1, "engine": engine, "image": "render.png", "width": 4, "height": 3}
        data.update(extra)
        (self.out / "manifest.json").write_text(json.dumps(data))

    def png(self, name="render.png", width=4, height=3):
        from PIL import Image
        Image.new("RGB", (width, height), "red").save(self.out / name)

    def test_swatch_only_is_not_a_render(self):
        self.png("tex_sample.png")
        with self.assertRaisesRegex(RuntimeError, "manifest"):
            agent.validate_render_output(self.out, self.error, 4, 3)
        self.manifest()
        with self.assertRaisesRegex(RuntimeError, "missing"):
            agent.validate_render_output(self.out, self.error, 4, 3)

    def test_error_wins_even_if_image_and_manifest_exist(self):
        self.png(); self.manifest(); self.error.write_text("Rhino failed to assign material")
        with self.assertRaisesRegex(RuntimeError, "assign material"):
            agent.validate_render_output(self.out, self.error, 4, 3)

    def test_bad_dimensions_and_bad_engine_fail(self):
        self.png(width=5); self.manifest()
        with self.assertRaisesRegex(RuntimeError, "requested"):
            agent.validate_render_output(self.out, self.error, 4, 3)
        self.png(); self.manifest(engine="Rhino Render")
        with self.assertRaisesRegex(RuntimeError, "V-Ray"):
            agent.validate_render_output(self.out, self.error, 4, 3)

    def test_complete_output_and_explicit_stub_opt_in(self):
        self.png(); self.manifest()
        self.assertEqual(agent.validate_render_output(self.out, self.error, 4, 3)[0].name, "render.png")
        self.manifest(engine="stub-rhino", simulation=True)
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "FF_ALLOW_STUB"):
                agent.validate_render_output(self.out, self.error, 4, 3)
        with mock.patch.dict(os.environ, {"FF_ALLOW_STUB": "1"}):
            self.assertEqual(agent.validate_render_output(self.out, self.error, 4, 3)[1]["engine"], "stub-rhino")


if __name__ == "__main__":
    unittest.main()
