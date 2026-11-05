"""Exercise the actual agent against a local API and explicitly synthetic Rhino stub."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import requests

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "The development stub is an executable Python script on Unix")
class WorkerTransportTest(unittest.TestCase):
    def test_analyze_and_render_with_labeled_stub(self):
        with tempfile.TemporaryDirectory(prefix="finishflow-transport-") as data:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            api = f"http://127.0.0.1:{port}"
            env = dict(os.environ, RENDER_RUNNER="agent", RENDER_DATA_DIR=data)
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                       "--port", str(port)], cwd=ROOT / "backend", env=env,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.addCleanup(self.stop, server)
            self.wait_for(lambda: self.healthy(api), server)
            worker_env = dict(os.environ, FF_API=api, FF_RHINO=str(ROOT / "worker/stub_rhino.py"),
                              FF_ALLOW_STUB="1", FF_POLL="0.2")
            worker = subprocess.Popen([sys.executable, "agent.py"], cwd=ROOT / "worker", env=worker_env,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.addCleanup(self.stop, worker)
            uploaded = requests.post(api + "/api/models", files={"file": ("stub.dwg", b"synthetic model")}, timeout=5)
            uploaded.raise_for_status()
            model_id, job_id = uploaded.json()["model"]["id"], uploaded.json()["job"]["id"]
            analyze = self.wait_for(lambda: self.job(api, job_id), worker)
            self.assertEqual(analyze["status"], "done", analyze)
            model = requests.get(api + f"/api/models/{model_id}", timeout=5).json()
            self.assertIn("stub-rhino", model["analyzer"])
            geometry = requests.get(api + model["structure"]["geometry_url"], timeout=5)
            self.assertEqual(len(geometry.json()["parts"]), 2)
            render = requests.post(api + "/api/jobs/render", json={"model_id": model_id,
                "settings": {"width": 64, "height": 48, "quality": "current", "camera": "top"}}, timeout=5)
            render.raise_for_status()
            result = self.wait_for(lambda: self.job(api, render.json()["id"]), worker)
            self.assertEqual(result["status"], "done", result)
            self.assertEqual(result["stage"], "Complete (simulated test)")
            gallery = requests.get(api + f"/api/renders?model_id={model_id}", timeout=5).json()
            self.assertEqual(gallery[0]["quality"], "current")
            self.assertEqual(gallery[0]["source"], "SIMULATED TEST")
            self.assertEqual((gallery[0]["width"], gallery[0]["height"]), (64, 48))

    @staticmethod
    def stop(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)

    @staticmethod
    def healthy(api):
        try:
            return requests.get(api + "/api/health", timeout=1).status_code == 200
        except requests.RequestException:
            return False

    @staticmethod
    def job(api, job_id):
        data = requests.get(api + f"/api/jobs/{job_id}", timeout=2).json()
        return data if data["status"] in ("done", "failed", "canceled") else None

    def wait_for(self, condition, process):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.fail(f"Test process exited unexpectedly with {process.returncode}")
            value = condition()
            if value:
                return value
            time.sleep(0.1)
        self.fail("Timed out waiting for synthetic worker transport")


if __name__ == "__main__":
    unittest.main()
