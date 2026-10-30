"""Dev fake worker — speaks the exact /api/agent/* protocol WITHOUT Rhino.

Purpose: validate the server side of the Rhino pipeline (job routing in auto mode,
claim → progress → complete/fail, analyze structures, preview + render uploads,
gallery rows) on any machine, including CI and Linux/macOS dev boxes:

    FF_API=http://localhost:8000 python dev_fake_worker.py

It claims jobs like the real agent and completes them:
  * analyze → structure parsed from the uploaded file when it is DXF (via the
    backend's dxfparse, if importable), otherwise a small demo structure; plus a
    generated preview PNG. Analyzer string is clearly marked "dev-fake-worker".
  * render  → generated gradient PNG at the requested size.

This is NOT the production worker. On the licensed Windows machine run agent.py,
which drives real Rhino 8 + V-Ray — see README.md.
"""
from __future__ import annotations

import json
import os
import socket
import struct
import sys
import time
import urllib.request
import uuid
import zlib
from pathlib import Path

try:
    import requests  # same dependency as agent.py
except ImportError:
    sys.exit("dev_fake_worker needs `requests` (pip install requests)")

API = os.environ.get("FF_API", "http://localhost:8000").rstrip("/")
POLL = float(os.environ.get("FF_POLL", "1.5"))
HERE = Path(__file__).resolve().parent

# allow importing the backend's real DXF parser for analyze jobs
sys.path.insert(0, str(HERE.parent / "backend"))


def log(*a):
    print("[fake-worker]", *a, flush=True)


# --------------------------------------------------------------------------- #
# tiny stdlib PNG writer (no PIL dependency on dev machines)
# --------------------------------------------------------------------------- #

def make_png(path: Path, w: int, h: int, kind: str) -> None:
    rows = bytearray()
    for y in range(h):
        rows.append(0)  # filter: none
        for x in range(w):
            if kind == "render":
                t = (x / max(1, w - 1) + y / max(1, h - 1)) / 2
                r, g, b = int(40 + 160 * t), int(35 + 90 * (1 - t)), int(60 + 120 * t)
            else:  # preview: checker
                c = 60 if ((x // 24) + (y // 24)) % 2 == 0 else 95
                r, g, b = c, c, c + 12
            rows += bytes((r, g, b))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
           + chunk(b"IEND", b""))
    path.write_bytes(png)


# --------------------------------------------------------------------------- #
# structure sources
# --------------------------------------------------------------------------- #

def demo_structure(name: str) -> dict:
    parts = [
        {"id": "p001", "name": "CASE BODY", "layer": "LAM-CASE", "block": None,
         "requires_block_edit": False, "bbox": {"min": [0, 0, 0], "max": [60, 24, 84]}},
        {"id": "p002", "name": "SHELF-ASSY #1", "layer": "LAM-SHELF", "block": "SHELF-ASSY",
         "requires_block_edit": True, "bbox": {"min": [4, 2, 30], "max": [56, 22, 42]}},
        {"id": "p003", "name": "ACCENT PANEL", "layer": "PET-ACCENT", "block": None,
         "requires_block_edit": False, "bbox": {"min": [2, 1, 42], "max": [58, 2, 80]}},
    ]
    return {
        "units": "inches",
        "source_file": name,
        "analyzer": "rhino8-worker 1.0 (dev-fake-worker — NOT real Rhino)",
        "extents": {"min": [0, 0, 0], "max": [60, 24, 84]},
        "layers": [
            {"name": "LAM-CASE", "color": "#b5651d", "part_count": 1},
            {"name": "LAM-SHELF", "color": "#ff7f00", "part_count": 1},
            {"name": "PET-ACCENT", "color": "#3a3a3a", "part_count": 1},
        ],
        "blocks": [{"name": "SHELF-ASSY", "instance_count": 1,
                    "layers": ["LAM-SHELF"], "part_ids": ["p002"]}],
        "parts": parts,
    }


def build_structure(model_path: Path, name: str) -> dict:
    head = b""
    try:
        head = model_path.read_bytes()[:6]
    except OSError:
        pass
    if head and not head.startswith(b"AC10"):
        try:
            from app import dxfparse  # backend on sys.path
            s = dxfparse.parse(str(model_path))
            s["analyzer"] = "rhino8-worker 1.0 (dev-fake-worker, dxf source — NOT real Rhino)"
            return s
        except Exception as exc:
            log("dxfparse unavailable/failed:", exc)
    return demo_structure(name)


# --------------------------------------------------------------------------- #
# protocol
# --------------------------------------------------------------------------- #

def download(url_rel: str, dest: Path) -> None:
    r = requests.get(API + url_rel, stream=True, timeout=120)
    r.raise_for_status()
    with open(dest, "wb") as fh:
        for chunk in r.iter_content(1 << 16):
            fh.write(chunk)


def progress(job_id: int, pct: int, stage: str) -> None:
    requests.post(f"{API}/api/agent/jobs/{job_id}/progress",
                  json={"progress": pct, "stage": stage}, timeout=10)


def do_analyze(job: dict, model: dict, td: Path) -> None:
    model_path = td / (model.get("original_name") or "model.bin")
    download(model["file_url"], model_path)
    progress(job["id"], 30, "dev-fake: importing")
    structure = build_structure(model_path, model.get("name", ""))
    progress(job["id"], 70, "dev-fake: structure built")
    preview = td / "preview.png"
    make_png(preview, 480, 360, "preview")
    with open(preview, "rb") as fh:
        r = requests.post(f"{API}/api/agent/jobs/{job['id']}/complete",
                          data={"structure": json.dumps(structure)},
                          files={"files": ("preview.png", fh, "image/png")}, timeout=60)
    r.raise_for_status()


def do_render(job: dict, settings: dict, td: Path) -> None:
    progress(job["id"], 25, "dev-fake: applying materials")
    time.sleep(1.0)
    progress(job["id"], 70, "dev-fake: rendering")
    w = min(int(settings.get("width", 960) or 960), 1280)
    h = min(int(settings.get("height", 600) or 600), 800)
    out = td / "render.png"
    make_png(out, w, h, "render")
    time.sleep(1.0)
    with open(out, "rb") as fh:
        r = requests.post(f"{API}/api/agent/jobs/{job['id']}/complete",
                          data={"duration_s": "2.0"},
                          files={"files": (out.name, fh, "image/png")}, timeout=60)
    r.raise_for_status()


def main() -> int:
    who = f"fake-{socket.gethostname()}"
    log(f"polling {API} as '{who}' every {POLL}s")
    while True:
        try:
            r = requests.get(f"{API}/api/agent/jobs/next", params={"name": who}, timeout=15)
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
        td = Path("/tmp") / f"ffake_{uuid.uuid4().hex[:8]}"
        td.mkdir(parents=True, exist_ok=True)
        try:
            if job["kind"] == "analyze":
                do_analyze(job, payload["model"], td)
            else:
                do_render(job, payload.get("settings", {}), td)
            log(f"job #{job['id']} complete")
        except Exception as exc:  # noqa: BLE001
            log(f"job #{job['id']} failed: {exc}")
            try:
                requests.post(f"{API}/api/agent/jobs/{job['id']}/fail",
                              json={"error": f"dev-fake-worker: {exc}"[:4000]}, timeout=15)
            except requests.RequestException:
                pass
        finally:
            for p in td.iterdir():
                p.unlink(missing_ok=True)
            td.rmdir()
    return 0


if __name__ == "__main__":
    sys.exit(main())
