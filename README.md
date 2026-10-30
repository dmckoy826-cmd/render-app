# FinishFlow — render automation for Rhino 8 + V-Ray

Web app for casework / fixture visualization: upload CAD models (DWG first-class, plus
anything AutoCAD/Rhino exports), upload PNG/JPG swatches of laminates, PET felts and
product finishes, map them onto the right parts of the model — by auto-match, by hand,
or with reusable presets — and queue renders that come back into a gallery.

The render back end is your **existing Rhino 8 + V-Ray licenses**, driven headlessly by a
worker agent on your Windows machine (`worker/`). Until the worker is connected, the
server runs a **built-in simulation engine** with the exact same job lifecycle, so the
whole workflow is usable and testable anywhere.

```
                        ┌───────────────────────────────┐
   browser (LAN) ─────► │  FastAPI server  (port 8000)  │
                        │  /api  jobs·models·finishes   │
                        │  /media  uploads·renders      │
                        └───────┬───────────────┬───────┘
                     RENDER_RUNNER=mock   RENDER_RUNNER=agent
                        │  simulated          │  polls /api/agent/*
                        │  Rhino/V-Ray        ▼
                        │               worker/agent.py (Windows)
                        │                 └─ Rhino 8 headless
                        ▼                    └─ V-Ray render (+ BlockEdit)
                   Pillow isometric
                   scene renderer
```

## Features

- **Models** — upload `.dwg .dxf .3dm .skp .obj .step …`; an analyze job extracts layers,
  block definitions (with instance counts) and parts with bounding boxes; isometric
  structure preview generated server-side. **DXF files are parsed for real** (ezdxf:
  true layers, colors, block instances, `$INSUNITS`, bounding boxes) even in simulated
  mode — including DXF content misnamed as `.dwg` (the file header is sniffed).
  Binary DWG cannot be read without Rhino, so it gets a simulated structure clearly
  labeled `SIM` in the UI until the Rhino worker is connected.
- **Finish library** — PNG/JPG swatches with category (laminate / PET / product finish),
  **real-world swatch size in inches** (drives texture scale everywhere), tags, seamless flag.
- **Mapping** — three levels: per **layer**, per **block definition** (applied via BlockEdit
  on the worker), per **part** override. Auto-match scores finishes against layer/block
  names (material tokens + category hints) with confidence percentages and manual override.
- **Presets** — save a model's mapping as pattern→finish rules (`contains / starts_with /
  exact / regex`) and apply to any future drawing in one click.
- **Job queue** — analyze + render jobs with staged progress, cancel, and runner badge
  (simulated vs Rhino agent).
- **Renders gallery** — results with the finish schedule used, resolution/quality/camera,
  download.
- **3D part viewer** — three.js orbit viewer; finishes are texture-mapped per face at
  their real-world scale; block-definition parts outlined in cyan; click to select.

## Quickstart (development / simulated engine)

```bash
# backend
cd backend
python3 -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
../.venv/bin/python seed.py          # demo finishes, models, preset, one render
../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# frontend
cd ../frontend
npm install
npm run dev                          # http://localhost:5173 (proxies /api, /media)
```

Open http://localhost:5173 — the seed provides a walnut reception desk and a storage
cabinet, nine procedural swatches, a preset and a finished render.

`seed.py --fresh` resets all data. Runtime data (DB, uploads, renders) lives in
`backend/data/` and is git-ignored.

## Connecting your real Rhino + V-Ray machine

See [`worker/README.md`](worker/README.md). Short version:

```bash
RENDER_RUNNER=agent ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000   # server
```
```bat
rem Windows box with the licenses
set FF_API=http://<server-ip>:8000
set FF_RHINO=C:\Program Files\Rhino 8\System\Rhino.exe
python worker\agent.py
```

## Layout

```
backend/app/          FastAPI app: models, finishes, presets, jobs, renders, agent API
backend/app/imaging.py   isometric scene renderer (occlusion-ordered painter, real
                         texture scale) used for previews + simulated renders
backend/app/mockdata.py  structure-contract generator standing in for Rhino analysis
backend/app/dxfparse.py  real DXF parser (ezdxf) → same structure contract
backend/seed.py       demo data
worker/               Rhino 8 worker agent + RhinoPython scripts (analyze, render)
frontend/             React + Vite + Tailwind + three.js UI
```

## Structure contract (analyze output)

```jsonc
{
  "units": "inches",
  "extents": { "min": [x, y, z], "max": [x, y, z] },
  "layers":  [{ "name", "color", "part_count" }],
  "blocks":  [{ "name", "instance_count", "layers", "part_ids" }],
  "parts":   [{ "id", "name", "layer", "block", "requires_block_edit",
                "bbox": { "min": [...], "max": [...] } }]
}
```

The simulator, the DXF parser and the Rhino worker all produce this document, so the UI
never changes when you switch engines. Each structure carries an `analyzer` string
(`mock-engine …`, `dxf-parser …`, `rhino8-worker …`) that the UI shows as a
SIM / DXF / RHINO badge so you always know whether the geometry is real.
