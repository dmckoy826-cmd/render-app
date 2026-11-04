#!/usr/bin/env python3
"""Dev stub for Rhino.exe — lets you test worker/agent.py's FULL transport on
Linux/macOS without Rhino installed.

Point the agent at it:
    FF_RHINO=/path/to/worker/stub_rhino.py FF_API=http://localhost:8000 python agent.py

The agent invokes it exactly like Rhino (`stub /nosplash /notemplate /runscript=...`)
and passes FF_* job env vars; this stub ignores the command line and does what the
RhinoPython scripts would do:
  * analyze job (FF_OUT_JSON set): writes a demo structure JSON + preview PNG
  * render job  (FF_OUT_DIR set): writes render.png at FF_WIDTH x FF_HEIGHT

Analyzer strings are marked "stub-rhino" so results are never mistaken for real
Rhino/V-Ray output. Requires only the Python 3 stdlib.
"""
import json
import os
import struct
import zlib


def make_png(path, w, h, kind):
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        for x in range(w):
            if kind == "render":
                t = (x / max(1, w - 1) + y / max(1, h - 1)) / 2
                r, g, b = int(30 + 150 * t), int(50 + 80 * (1 - t)), int(70 + 110 * t)
            else:
                c = 55 if ((x // 20) + (y // 20)) % 2 == 0 else 90
                r, g, b = c, c, c + 10
            rows += bytes((r, g, b))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
           + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


def do_analyze():
    out_json = os.environ["FF_OUT_JSON"]
    out_png = os.environ.get("FF_OUT_PNG", "")
    model = os.environ.get("FF_MODEL", "model")
    structure = {
        "units": "inches",
        "source_file": os.path.basename(model),
        "analyzer": "rhino8-worker 1.0 (stub-rhino transport test — NOT real Rhino)",
        "extents": {"min": [0, 0, 0], "max": [48, 20, 72]},
        "layers": [
            {"name": "STUB-CASE", "color": "#b5651d", "part_count": 1},
            {"name": "STUB-TRIM", "color": "#c0c0c0", "part_count": 1},
        ],
        "blocks": [{"name": "STUB-BLOCK", "instance_count": 1,
                    "layers": ["STUB-TRIM"], "part_ids": ["p002"]}],
        "parts": [
            {"id": "p001", "name": "case body", "layer": "STUB-CASE", "block": None,
             "requires_block_edit": False, "bbox": {"min": [0, 0, 0], "max": [48, 20, 72]}},
            {"id": "p002", "name": "STUB-BLOCK #1", "layer": "STUB-TRIM", "block": "STUB-BLOCK",
             "requires_block_edit": True, "bbox": {"min": [4, 2, 30], "max": [44, 18, 40]}},
        ],
    }
    with open(out_json, "w") as fh:
        json.dump(structure, fh)
    if out_png:
        make_png(out_png, 400, 300, "preview")
    print("ANALYZE_OK 2 parts (stub)")


def do_render():
    out_dir = os.environ["FF_OUT_DIR"]
    w = min(int(os.environ.get("FF_WIDTH", "640")), 1280)
    h = min(int(os.environ.get("FF_HEIGHT", "400")), 800)
    os.makedirs(out_dir, exist_ok=True)
    make_png(os.path.join(out_dir, "render.png"), w, h, "render")
    print("RENDER_OK %dx%d (stub)" % (w, h))


if os.environ.get("FF_OUT_JSON"):
    do_analyze()
elif os.environ.get("FF_OUT_DIR"):
    do_render()
else:
    print("stub_rhino: no FF_OUT_JSON / FF_OUT_DIR in environment — nothing to do")
