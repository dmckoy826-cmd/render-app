"""FinishFlow Rhino worker agent.

Runs on the Windows machine that holds your Rhino 8 + V-Ray licenses. It polls the
FinishFlow server for jobs, executes them headlessly in Rhino, and posts results back.

Setup (on the Rhino machine):
    pip install requests
    set FF_API=http://<server-lan-ip>:8000
    set FF_RHINO=C:\Program Files\Rhino 8\System\Rhino.exe
    python agent.py

The server defaults to RENDER_RUNNER=auto: while this agent is polling (its heartbeat
is tracked server-side), jobs route to it; if it goes away, the server falls back to
the built-in simulation engine so the UI keeps working. Set RENDER_RUNNER=agent to
force jobs to wait for a real worker only.
"""
from __future__ import annotations

import json
import os
import subprocess
import struct
import sys
import threading
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


def run_rhino(script: Path, env: dict, timeout: float = 3600) -> str:
    """Launch Rhino and execute a RhinoPython script; return its console output.

    Command line follows the McNeel-documented pattern for paths with spaces:
    the script path is wrapped in PARENTHESES inside the runscript macro, and
    `_Exit` closes Rhino when the script finishes (each script clears the
    document's Modified flag so no save prompt can block the exit).
    `/notemplate` skips the startup template/units dialog.
    """
    e = {**os.environ, **env}
    if os.name == "nt":
        # Pass a raw command string on Windows so subprocess.list2cmdline does
        # not wrap the entire /runscript=... switch in outer quotes, which
        # causes Rhino 8 to ignore /runscript.
        cmd = f'"{RHINO}" /nosplash /notemplate /runscript="-_RunPythonScript ({script}) _Exit"'
        log("exec:", cmd)
    else:
        cmd = [RHINO, "/nosplash", "/notemplate",
               f"/runscript=-_RunPythonScript ({script}) _Exit"]
        log("exec:", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, env=e, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Rhino timed out after {timeout:.0f}s (job may be too large "
                           f"or Rhino showed a modal dialog)") from exc
    out = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
    if proc.returncode != 0:
        raise RuntimeError(f"Rhino exited {proc.returncode}: {out[-2000:]}")
    return out


def progress(job_id: int, pct: int, stage: str) -> None:
    try:
        requests.post(f"{API}/api/agent/jobs/{job_id}/progress",
                      json={"progress": pct, "stage": stage}, timeout=10)
    except requests.RequestException:
        pass


def script_error(path: Path, fallback: str) -> RuntimeError:
    if path.exists():
        return RuntimeError(path.read_text(encoding="utf-8", errors="replace")[-3500:])
    return RuntimeError(fallback)


def png_size(path: Path) -> tuple[int, int]:
    with open(path, "rb") as fh:
        header = fh.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise RuntimeError("The render output is not a valid PNG.")
    return struct.unpack(">II", header[16:24])


def validate_render_output(out_dir: Path, error: Path, width: int, height: int) -> tuple[Path, dict]:
    if error.exists():
        raise script_error(error, "Rhino render failed.")
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Rhino did not produce a completed render manifest. No render was uploaded.")
    try:
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise RuntimeError("Rhino produced an invalid render manifest.") from exc
    is_stub = (meta.get("engine") == "stub-rhino" and meta.get("simulation") is True
               and os.environ.get("FF_ALLOW_STUB") == "1")
    if meta.get("protocol") != 1 or (meta.get("engine") != "V-Ray" and not is_stub):
        raise RuntimeError("The render was not confirmed as V-Ray (stub requires FF_ALLOW_STUB=1).")
    if meta.get("image") != "render.png":
        raise RuntimeError("Render manifest does not name render.png.")
    image = out_dir / "render.png"
    if not image.is_file() or png_size(image) != (width, height):
        raise RuntimeError(f"Render image is missing or not the requested {width}x{height} size.")
    if (meta.get("width"), meta.get("height")) != (width, height):
        raise RuntimeError("Render manifest dimensions do not match the requested size.")
    return image, meta


def do_analyze(job: dict, model: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="ff_") as td:
        td = Path(td)
        filename = Path((model.get("original_name") or "model.dwg").replace("\\", "/")).name
        model_path = td / (filename or "model.dwg")
        download(model["file_url"], model_path)
        out_json = td / "structure.json"
        out_png = td / "preview.png"
        out_geometry = td / "geometry.json"
        progress(job["id"], 10, "Worker: importing model")
        console = run_rhino(HERE / "rhino_scripts" / "analyze_model.py", {
            "FF_MODEL": str(model_path), "FF_OUT_JSON": str(out_json),
            "FF_OUT_PNG": str(out_png), "FF_OUT_GEOMETRY": str(out_geometry),
        })
        error = Path(str(out_json) + ".error.txt")
        if error.exists() or not out_json.exists():
            raise script_error(error, f"Rhino produced no structure.json. Console: {console[-1500:]}")
        structure = json.loads(out_json.read_text(encoding="utf-8"))
        if structure.get("target_schema") != "rhino-geometry-v1" or not out_geometry.is_file():
            raise RuntimeError("Rhino analysis did not produce the expected structure and geometry preview.")
        progress(job["id"], 90, "Uploading structure and geometry")
        with open(out_geometry, "rb") as geometry:
            files = [("geometry", ("geometry.json", geometry, "application/json"))]
            if out_png.exists():
                with open(out_png, "rb") as preview:
                    files.append(("files", ("preview.png", preview, "image/png")))
                    r = requests.post(f"{API}/api/agent/jobs/{job['id']}/complete",
                                      data={"structure": json.dumps(structure)}, files=files, timeout=300)
            else:
                r = requests.post(f"{API}/api/agent/jobs/{job['id']}/complete",
                                  data={"structure": json.dumps(structure)}, files=files, timeout=300)
        r.raise_for_status()


def do_render(job: dict, model: dict, settings: dict, assignments: list) -> None:
    if (model.get("structure") or {}).get("target_schema") != "rhino-geometry-v1":
        raise RuntimeError("Re-analyze this model with the updated Rhino worker before rendering.")
    with tempfile.TemporaryDirectory(prefix="ff_") as td:
        td = Path(td)
        filename = Path((model.get("original_name") or "model.dwg").replace("\\", "/")).name
        model_path = td / (filename or "model.dwg")
        if not model.get("file_url"):
            raise RuntimeError("Model file is missing.")
        download(model["file_url"], model_path)
        assign_path = td / "assignments.json"
        assign_path.write_text(json.dumps(assignments), encoding="utf-8")
        structure_path = td / "structure.json"
        structure_path.write_text(json.dumps(model["structure"]), encoding="utf-8")
        out_dir, tex_dir = td / "results", td / "textures"
        out_dir.mkdir()
        tex_dir.mkdir()
        error = td / "rhino_error.txt"
        width, height = int(settings.get("width", 1920)), int(settings.get("height", 1080))
        progress(job["id"], 5, "Worker: preparing model and materials")
        console = run_rhino(HERE / "rhino_scripts" / "render_model.py", {
            "FF_MODEL": str(model_path), "FF_ASSIGNMENTS": str(assign_path),
            "FF_STRUCTURE": str(structure_path), "FF_OUT_DIR": str(out_dir),
            "FF_TEX_DIR": str(tex_dir), "FF_ERROR": str(error),
            "FF_WIDTH": str(width), "FF_HEIGHT": str(height),
            "FF_QUALITY": str(settings.get("quality", "current")),
            "FF_CAMERA": str(settings.get("camera", "iso")),
            "FF_API": API,
        })
        if error.exists():
            raise script_error(error, "Rhino render failed.")
        try:
            image, meta = validate_render_output(out_dir, error, width, height)
        except RuntimeError as exc:
            raise RuntimeError(f"{exc} Rhino console: {console[-1200:]}") from exc
        progress(job["id"], 92, "Uploading verified render")
        with open(image, "rb") as fh:
            r = requests.post(f"{API}/api/agent/jobs/{job['id']}/complete",
                              data={"manifest": json.dumps(meta)},
                              files={"files": ("render.png", fh, "image/png")}, timeout=300)
        r.raise_for_status()


def heartbeat_while_busy(stop: threading.Event, name: str) -> None:
    # Polling /jobs/next while busy would claim another job, so use a dedicated beat.
    while not stop.wait(20):
        try:
            requests.post(f"{API}/api/agent/heartbeat", json={"name": name}, timeout=10)
        except requests.RequestException:
            pass


def main() -> int:
    import socket
    who = socket.gethostname()
    log(f"polling {API} every {POLL}s as '{who}' (Rhino: {RHINO})")
    log("Server auto mode can simulate when no worker is connected; use RENDER_RUNNER=agent to wait instead.")
    while True:
        try:
            r = requests.get(f"{API}/api/agent/jobs/next", params={"name": who}, timeout=30)
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
        stop = threading.Event()
        thread = threading.Thread(target=heartbeat_while_busy, args=(stop, who), daemon=True)
        thread.start()
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
        finally:
            stop.set()
            thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
