"""FinishFlow Rhino worker agent.

Runs on the Windows machine that holds your Rhino 8 + V-Ray licenses. It polls the
FinishFlow server for jobs, executes them headlessly in Rhino, and posts results back.

Setup (on the Rhino machine):
    pip install requests
    set FF_API=http://<server-lan-ip>:8000
    set FF_RHINO=C:\Program Files\Rhino 8\System\Rhino.exe
    python agent.py

The server must run with RENDER_RUNNER=agent so jobs queue for this worker instead of
the built-in simulation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

API = os.environ.get("FF_API", "http://localhost:8000").rstrip("/")
RHINO = os.environ.get("FF_RHINO", r"C:\Program Files\Rhino 8\System\Rhino.exe")
POLL = float(os.environ.get("FF_POLL", "3"))
HERE = Path(__file__).resolve().parent


def log(*a):
    print("[agent]", *a, flush=True)


def download(url: str, dest: Path) -> None:
    r = requests.get(API + url, stream=True, timeout=120)
    r.raise_for_status()
    with open(dest, "wb") as fh:
        for chunk in r.iter_content(1 << 16):
            fh.write(chunk)


def run_rhino(script: Path, env: dict) -> None:
    """Launch headless Rhino and execute a RhinoPython script.

    Rhino 8 accepts /runscript on the command line; the script path is quoted and
    terminated with `_` so the command line returns. The script itself reads its job
    parameters from the environment (FF_*).
    """
    e = {**os.environ, **env}
    cmd = [RHINO, "/nosplash", f'/runscript=-_RunPythonScript "{script}" _']
    log("exec:", " ".join(cmd))
    proc = subprocess.run(cmd, env=e, capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0:
        raise RuntimeError(f"Rhino exited {proc.returncode}: {proc.stdout[-2000:]} {proc.stderr[-2000:]}")


def progress(job_id: int, pct: int, stage: str) -> None:
    try:
        requests.post(f"{API}/api/agent/jobs/{job_id}/progress",
                      json={"progress": pct, "stage": stage}, timeout=10)
    except requests.RequestException:
        pass


def do_analyze(job: dict, model: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="ff_") as td:
        td = Path(td)
        model_path = td / (model["original_name"] or "model.dwg")
        download(model["file_url"], model_path)
        out_json = td / "structure.json"
        out_png = td / "preview.png"
        progress(job["id"], 10, "Importing in Rhino 8")
        run_rhino(HERE / "rhino_scripts" / "analyze_model.py", {
            "FF_MODEL": str(model_path),
            "FF_OUT_JSON": str(out_json),
            "FF_OUT_PNG": str(out_png),
        })
        structure = json.loads(out_json.read_text())
        progress(job["id"], 90, "Uploading structure")
        with open(out_png, "rb") as fh:
            r = requests.post(f"{API}/api/agent/jobs/{job['id']}/complete",
                              data={"structure": json.dumps(structure)},
                              files={"files": ("preview.png", fh, "image/png")}, timeout=120)
        r.raise_for_status()


def do_render(job: dict, model: dict, settings: dict, assignments: list) -> None:
    with tempfile.TemporaryDirectory(prefix="ff_") as td:
        td = Path(td)
        model_path = td / (model["original_name"] or "model.dwg")
        if model.get("file_url"):
            download(model["file_url"], model_path)
        assign_path = td / "assignments.json"
        assign_path.write_text(json.dumps(assignments))
        out_dir = td / "out"
        out_dir.mkdir()
        progress(job["id"], 5, "Rhino 8: applying V-Ray materials")
        run_rhino(HERE / "rhino_scripts" / "render_model.py", {
            "FF_MODEL": str(model_path),
            "FF_ASSIGNMENTS": str(assign_path),
            "FF_OUT_DIR": str(out_dir),
            "FF_WIDTH": str(settings.get("width", 1920)),
            "FF_HEIGHT": str(settings.get("height", 1080)),
            "FF_QUALITY": str(settings.get("quality", "standard")),
            "FF_CAMERA": str(settings.get("camera", "iso")),
        })
        imgs = sorted(out_dir.glob("*.png")) + sorted(out_dir.glob("*.jpg"))
        if not imgs:
            raise RuntimeError("render script produced no images")
        progress(job["id"], 92, "Uploading renders")
        files = [("files", (p.name, open(p, "rb"), "image/png")) for p in imgs]
        try:
            r = requests.post(f"{API}/api/agent/jobs/{job['id']}/complete",
                              files=files, timeout=300)
            r.raise_for_status()
        finally:
            for _, (_, fh, _) in files:
                fh.close()


def main() -> int:
    log(f"polling {API} every {POLL}s (Rhino: {RHINO})")
    while True:
        try:
            r = requests.get(f"{API}/api/agent/jobs/next", timeout=30)
            r.raise_for_status()
            payload = r.json()
        except requests.RequestException as exc:
            log("server unreachable:", exc)
            time.sleep(POLL * 2)
            continue
        job = payload.get("job")
        if not job:
            time.sleep(POLL)
            continue
        log(f"claimed job #{job['id']} ({job['kind']})")
        try:
            if job["kind"] == "analyze":
                do_analyze(job, payload["model"])
            else:
                do_render(job, payload["model"], payload.get("settings", {}),
                          payload.get("assignments", []))
            log(f"job #{job['id']} complete")
        except Exception as exc:  # noqa: BLE001
            log(f"job #{job['id']} failed: {exc}")
            try:
                requests.post(f"{API}/api/agent/jobs/{job['id']}/fail",
                              json={"error": str(exc)[:4000]}, timeout=15)
            except requests.RequestException:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
