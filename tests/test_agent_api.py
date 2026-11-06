"""HTTP protocol tests using a temporary SQLite DB and synthetic images, not Rhino."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

TEMP = tempfile.TemporaryDirectory(prefix="finishflow-tests-")
os.environ["RENDER_DATA_DIR"] = TEMP.name
os.environ["RENDER_RUNNER"] = "agent"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from fastapi.testclient import TestClient
from PIL import Image
from app.config import MEDIA_DIR
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Assignment, Finish, Job, ModelDoc, Preset, Render


def png(width=8, height=6):
    out = io.BytesIO()
    Image.new("RGB", (width, height), "blue").save(out, format="PNG")
    return out.getvalue()


def structure(schema=True):
    data = {"analyzer": "rhino8-worker 2.0", "units": "inches",
            "extents": {"min": [0, 0, 0], "max": [1, 1, 1]},
            "layers": [{"name": "L1", "color": "#ffffff", "part_count": 1}], "blocks": [],
            "parts": [{"id": "p1", "name": "panel", "layer": "L1", "block": None,
                       "requires_block_edit": False, "bbox": {"min": [0, 0, 0], "max": [1, 1, 1]}}]}
    if schema:
        data["target_schema"] = "rhino-geometry-v1"
    return data


def geometry():
    return {"version": 1, "units": "inches", "parts": [
        {"id": "p1", "positions": [0, 0, 0, 1, 0, 0, 0, 1, 0], "triangles": [0, 1, 2], "lines": []}]}


def manifest(engine_name="V-Ray"):
    return {"protocol": 1, "engine": engine_name, "image": "render.png", "width": 8, "height": 6}


class AgentApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        engine.dispose()
        TEMP.cleanup()

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def job(self, kind, analyzed=True, status="running"):
        with SessionLocal() as db:
            model = ModelDoc(name="test", original_name="test.dwg", storage_path="models/test.dwg",
                             status="ready", structure=structure(analyzed))
            db.add(model); db.commit(); db.refresh(model)
            job = Job(kind=kind, model_id=model.id, status=status, runner="agent",
                      settings={"width": 8, "height": 6, "quality": "current", "camera": "top"})
            db.add(job); db.commit(); db.refresh(job)
            return model.id, job.id

    def test_geometry_uploaded_separately_and_served(self):
        model_id, job_id = self.job("analyze")
        response = self.client.post(f"/api/agent/jobs/{job_id}/complete", data={"structure": json.dumps(structure())},
            files=[("geometry", ("geometry.json", json.dumps(geometry()), "application/json")),
                   ("files", ("preview.png", png(), "image/png"))])
        self.assertEqual(response.status_code, 200, response.text)
        model = self.client.get(f"/api/models/{model_id}").json()
        self.assertTrue(model["structure"]["geometry_url"].startswith("/media/geometry/"))
        self.assertNotIn("positions", json.dumps(model["structure"]))
        self.assertEqual(self.client.get(model["structure"]["geometry_url"]).json(), geometry())
        self.assertEqual(model["status"], "ready")

    def test_geometry_preview_endpoint_filters_sku_and_part_layers(self):
        model_id, job_id = self.job("analyze")
        structure_data = structure()
        structure_data["preview_schema"] = 2
        structure_data["sku_layers"] = [
            {"name": "SKU-A::Body", "part_layers": ["L1"]},
            {"name": "SKU-B::Body", "part_layers": ["L2"]},
        ]
        structure_data["parts"][0]["sku_layers"] = ["SKU-A", "SKU-B"]
        mesh = {"positions": [0, 0, 0, 1, 0, 0, 0, 1, 0], "triangles": [0, 1, 2], "lines": []}
        payload = {"version": 1, "units": "inches", "parts": [
            {"id": "p1", "layer": "L1", "sku_layer": "SKU-A::Body", **mesh},
            {"id": "p1", "layer": "L2", "sku_layer": "SKU-B::Body", **mesh},
        ]}
        response = self.client.post(f"/api/agent/jobs/{job_id}/complete",
            data={"structure": json.dumps(structure_data)},
            files={"geometry": ("geometry.json", json.dumps(payload), "application/json")})
        self.assertEqual(response.status_code, 200, response.text)
        model = self.client.get(f"/api/models/{model_id}").json()
        api_url = model["structure"]["geometry_api_url"]
        by_sku = self.client.get(api_url, params={"sku_layer": "SKU-B"}).json()
        self.assertEqual([part["sku_layer"] for part in by_sku["parts"]], ["SKU-B::Body"])
        by_layer = self.client.get(api_url, params={"layer": "L1"}).json()
        self.assertEqual([part["layer"] for part in by_layer["parts"]], ["L1"])

    def test_analysis_requires_valid_geometry_and_rejects_bad_indices(self):
        _, job_id = self.job("analyze")
        r = self.client.post(f"/api/agent/jobs/{job_id}/complete", data={"structure": json.dumps(structure())})
        self.assertEqual(r.status_code, 400)
        bad = geometry(); bad["parts"][0]["triangles"] = [0, 1, 99]
        r = self.client.post(f"/api/agent/jobs/{job_id}/complete", data={"structure": json.dumps(structure())},
                             files={"geometry": ("geometry.json", json.dumps(bad), "application/json")})
        self.assertEqual(r.status_code, 400)
        self.assertIn("index", r.text)
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}").json()["status"], "running")

    def test_render_rejects_no_image_swatch_missing_manifest_and_wrong_size(self):
        _, job_id = self.job("render")
        url = f"/api/agent/jobs/{job_id}/complete"
        self.assertEqual(self.client.post(url).status_code, 400)
        self.assertEqual(self.client.post(url, data={"manifest": json.dumps(manifest())}).status_code, 400)
        self.assertEqual(self.client.post(url, files={"files": ("render.png", png(), "image/png")}).status_code, 400)
        self.assertEqual(self.client.post(url, data={"manifest": json.dumps(manifest())},
            files={"files": ("tex_swatch.png", png(), "image/png")}).status_code, 400)
        self.assertEqual(self.client.post(url, data={"manifest": json.dumps(manifest())},
            files={"files": ("render.png", png(7, 6), "image/png")}).status_code, 400)
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}").json()["status"], "running")

    def test_render_success_and_simulated_stub_are_labeled(self):
        model_id, job_id = self.job("render")
        fake = dict(manifest("stub-rhino"), simulation=True)
        r = self.client.post(f"/api/agent/jobs/{job_id}/complete", data={"manifest": json.dumps(fake)},
                             files={"files": ("render.png", png(), "image/png")})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["stage"], "Complete (simulated test)")
        renders = self.client.get(f"/api/renders?model_id={model_id}").json()
        self.assertEqual(len(renders), 1)
        self.assertEqual(renders[0]["quality"], "current")
        self.assertEqual(renders[0]["source"], "SIMULATED TEST")
        self.assertEqual((renders[0]["width"], renders[0]["height"]), (8, 6))

    def test_stale_analysis_and_quality_are_rejected_before_queue(self):
        model_id, _ = self.job("analyze", analyzed=False, status="done")
        settings = {"width": 8, "height": 6, "quality": "current", "camera": "top"}
        r = self.client.post("/api/jobs/render", json={"model_id": model_id, "settings": settings})
        self.assertEqual(r.status_code, 409)
        self.assertIn("Re-analyze", r.text)
        model_id, _ = self.job("analyze", status="done")
        settings["quality"] = "standard"
        r = self.client.post("/api/jobs/render", json={"model_id": model_id, "settings": settings})
        self.assertEqual(r.status_code, 409)
        self.assertIn("current settings", r.text)

    def test_canceled_job_cannot_be_overwritten_by_late_worker_error(self):
        _, job_id = self.job("render", status="canceled")
        self.assertEqual(self.client.post(f"/api/agent/jobs/{job_id}/fail", json={"error": "late"}).status_code, 409)
        self.assertEqual(self.client.post(f"/api/agent/jobs/{job_id}/progress", json={"progress": 90}).status_code, 409)
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}").json()["status"], "canceled")

    def test_worker_snapshot_survives_assignment_changes(self):
        model_id, job_id = self.job("render", status="queued")
        with SessionLocal() as db:
            f = Finish(name="Original", category="laminate", original_name="x.png",
                       storage_path="finishes/x.png", thumb_path="", swatch_width_in=12, swatch_height_in=12)
            db.add(f); db.commit(); db.refresh(f)
            db.add(Assignment(model_id=model_id, target_kind="layer", target_name="L1", finish_id=f.id))
            db.commit()
        claimed = self.client.get("/api/agent/jobs/next?name=test").json()
        self.assertEqual(claimed["job"]["id"], job_id)
        self.assertEqual(claimed["assignments"][0]["finish"]["name"], "Original")
        with SessionLocal() as db:
            db.query(Assignment).filter(Assignment.model_id == model_id).delete()
            db.commit()
        r = self.client.post(f"/api/agent/jobs/{job_id}/complete", data={"manifest": json.dumps(manifest())},
                             files={"files": ("render.png", png(), "image/png")})
        self.assertEqual(r.status_code, 200, r.text)
        render = self.client.get(f"/api/renders?model_id={model_id}").json()[0]
        self.assertEqual(render["source"], "V-RAY REPORTED")
        self.assertEqual(render["finishes"][0]["name"], "Original")
        self.assertEqual(render["finishes"][0]["targets"], ["layer:L1"])

    def test_queue_freezes_assignments_before_worker_claims_job(self):
        model_id, _ = self.job("analyze", status="done")
        with SessionLocal() as db:
            finish = Finish(name="Before queue", category="laminate", original_name="x.png",
                            storage_path="finishes/x.png", thumb_path="", swatch_width_in=12, swatch_height_in=12)
            db.add(finish); db.commit(); db.refresh(finish)
            db.add(Assignment(model_id=model_id, target_kind="layer", target_name="L1", finish_id=finish.id))
            db.commit()
        settings = {"width": 8, "height": 6, "quality": "current", "camera": "top"}
        queued = self.client.post("/api/jobs/render", json={"model_id": model_id, "settings": settings})
        self.assertEqual(queued.status_code, 200, queued.text)
        with SessionLocal() as db:
            db.query(Assignment).filter(Assignment.model_id == model_id).delete()
            db.commit()
        claimed = self.client.get("/api/agent/jobs/next?name=worker").json()
        self.assertEqual(claimed["assignments"][0]["finish"]["name"], "Before queue")

    def test_old_geometry_is_removed_after_reanalysis(self):
        model_id, first_id = self.job("analyze")
        fields = {"structure": json.dumps(structure())}
        files = lambda: [("geometry", ("geometry.json", json.dumps(geometry()), "application/json")),
                         ("files", ("preview.png", png(), "image/png"))]
        first = self.client.post(f"/api/agent/jobs/{first_id}/complete", data=fields, files=files())
        self.assertEqual(first.status_code, 200, first.text)
        old_url = self.client.get(f"/api/models/{model_id}").json()["structure"]["geometry_url"]
        with SessionLocal() as db:
            next_job = Job(kind="analyze", model_id=model_id, status="running", runner="agent", settings={})
            db.add(next_job); db.commit(); db.refresh(next_job); second_id = next_job.id
        second = self.client.post(f"/api/agent/jobs/{second_id}/complete", data=fields, files=files())
        self.assertEqual(second.status_code, 200, second.text)
        new_url = self.client.get(f"/api/models/{model_id}").json()["structure"]["geometry_url"]
        self.assertNotEqual(old_url, new_url)
        self.assertEqual(self.client.get(old_url).status_code, 404)
        self.assertEqual(self.client.get(new_url).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/models/{model_id}").status_code, 200)
        self.assertEqual(self.client.get(new_url).status_code, 404)

    def test_manual_targets_and_part_presets_use_stable_ids(self):
        model_id, _ = self.job("analyze", status="done")
        with SessionLocal() as db:
            finish = Finish(name="Walnut", category="laminate", original_name="x.png",
                            storage_path="finishes/x.png", thumb_path="", swatch_width_in=12, swatch_height_in=12)
            db.add(finish); db.commit(); db.refresh(finish)
            fid = finish.id
            preset = Preset(name="Part rule", rules=[{"target_kind": "part", "match": "exact",
                                                       "pattern": "panel", "finish_id": fid}])
            db.add(preset); db.commit(); db.refresh(preset); pid = preset.id
        bad = self.client.post(f"/api/models/{model_id}/assignments", json={"target_kind": "part", "target_name": "panel", "finish_id": fid})
        self.assertEqual(bad.status_code, 409)
        r = self.client.post(f"/api/models/{model_id}/presets/{pid}/apply", json={"overwrite": False})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["matches"][0]["target_name"], "p1")
        self.assertEqual(r.json()["assignments"][0]["target_name"], "p1")

    def test_saved_part_preset_is_exact_and_preserves_scale(self):
        model_id, _ = self.job("analyze", status="done")
        with SessionLocal() as db:
            model = db.get(ModelDoc, model_id)
            data = dict(model.structure)
            data["parts"] = [*data["parts"], dict(data["parts"][0], id="p2")]
            model.structure = data
            finish = Finish(name="Walnut", category="laminate", original_name="x.png", storage_path="finishes/x.png",
                            thumb_path="", swatch_width_in=12, swatch_height_in=12)
            db.add(finish); db.commit(); db.refresh(finish); fid = finish.id
        request = {"target_kind": "part", "target_name": "p1", "finish_id": fid, "scale_multiplier": 2.5}
        self.assertEqual(self.client.post(f"/api/models/{model_id}/assignments", json=request).status_code, 200)
        saved = self.client.post("/api/presets/from-model", json={"model_id": model_id, "name": "Only one panel"})
        self.assertEqual(saved.status_code, 200, saved.text)
        rule = saved.json()["rules"][0]
        self.assertEqual((rule["target_property"], rule["match"], rule["pattern"], rule["scale_multiplier"]),
                         ("identity", "exact", "p1", 2.5))
        self.client.post(f"/api/models/{model_id}/assignments", json=dict(request, finish_id=None))
        applied = self.client.post(f"/api/models/{model_id}/presets/{saved.json()['id']}/apply", json={"overwrite": True}).json()
        self.assertEqual(applied["applied"], 1)
        self.assertEqual(applied["assignments"][0]["target_name"], "p1")
        self.assertEqual(applied["assignments"][0]["scale_multiplier"], 2.5)
        unsafe = self.client.post("/api/presets", json={"name": "Unsafe", "rules": [{"target_kind": "part",
            "target_property": "identity", "match": "contains", "pattern": "p", "finish_id": fid}]})
        self.assertEqual(unsafe.status_code, 422)

    def test_swatch_upload_rejects_corrupt_or_misnamed_images(self):
        invalid = self.client.post("/api/finishes", files={"file": ("bad.png", b"not an image", "image/png")})
        self.assertEqual(invalid.status_code, 400)
        misnamed = self.client.post("/api/finishes", files={"file": ("bad.jpg", png(), "image/jpeg")})
        self.assertEqual(misnamed.status_code, 400)
        valid = self.client.post("/api/finishes", files={"file": ("good.png", png(), "image/png")},
                                 data={"swatch_width_in": "12", "swatch_height_in": "12"})
        self.assertEqual(valid.status_code, 200, valid.text)

    def test_swatch_upload_requires_real_world_dimensions(self):
        """A missing size must be rejected, not silently defaulted — a wrong size
        silently mis-scales every texture that uses the swatch."""
        missing = self.client.post("/api/finishes",
                                   files={"file": ("nosize.png", png(), "image/png")})
        self.assertEqual(missing.status_code, 400, missing.text)
        self.assertIn("dimensions", missing.json()["detail"])

        partial = self.client.post("/api/finishes", files={"file": ("half.png", png(), "image/png")},
                                   data={"swatch_width_in": "48"})
        self.assertEqual(partial.status_code, 400, partial.text)

        zero = self.client.post("/api/finishes", files={"file": ("zero.png", png(), "image/png")},
                                data={"swatch_width_in": "0", "swatch_height_in": "48"})
        self.assertEqual(zero.status_code, 400, zero.text)

        ok = self.client.post("/api/finishes", files={"file": ("ok.png", png(), "image/png")},
                              data={"swatch_width_in": "48", "swatch_height_in": "96"})
        self.assertEqual(ok.status_code, 200, ok.text)
        body = ok.json()
        self.assertEqual(body["swatch_width_in"], 48.0)
        self.assertEqual(body["swatch_height_in"], 96.0)

    def test_automatch_distinguishes_same_layer_and_block_name(self):
        model_id, _ = self.job("analyze", status="done")
        with SessionLocal() as db:
            model = db.get(ModelDoc, model_id)
            data = dict(model.structure)
            data["layers"] = [{"name": "WALNUT", "color": "#ffffff", "part_count": 1}]
            data["blocks"] = [{"name": "WALNUT", "part_ids": ["p1"], "instance_count": 1, "layers": ["WALNUT"]}]
            model.structure = data
            db.add(Finish(name="Walnut", category="laminate", original_name="x.png", storage_path="finishes/x.png",
                          thumb_path="", swatch_width_in=12, swatch_height_in=12))
            db.commit()
        response = self.client.get(f"/api/models/{model_id}/automatch?min_score=0.3")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({(s["target_kind"], s["target_name"]) for s in response.json()},
                         {("layer", "WALNUT"), ("block", "WALNUT")})

    def test_heartbeat_does_not_claim_jobs(self):
        _, job_id = self.job("render", status="queued")
        self.assertEqual(self.client.post("/api/agent/heartbeat", json={"name": "busy"}).status_code, 200)
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}").json()["status"], "queued")
        self.assertEqual(self.client.get("/api/system/info").json()["agent_name"], "busy")


if __name__ == "__main__":
    unittest.main()
