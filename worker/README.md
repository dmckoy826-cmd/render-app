# Rhino / V-Ray worker

This folder turns the **simulated** render engine into a **real** one by driving your
licensed Rhino 8 + V-Ray installation headlessly on a Windows machine in your LAN.

```
browser  →  FinishFlow server (FastAPI, LAN)  ⇄  worker/agent.py  →  Rhino 8 (headless)
                                   job queue        polls /api/agent/*      └─ V-Ray render
```

## 1. Server side

Run the backend with the agent runner so jobs wait for Rhino instead of being simulated:

```bash
RENDER_RUNNER=agent ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Everything else (uploads, mapping UI, presets, gallery) is unchanged — the UI shows
“Rhino worker agent” in the sidebar once `RENDER_RUNNER=agent`.

## 2. Worker side (Windows machine with the licenses)

```bat
pip install requests
set FF_API=http://<server-lan-ip>:8000
set FF_RHINO=C:\Program Files\Rhino 8\System\Rhino.exe
python agent.py
```

The agent polls `GET /api/agent/jobs/next`, downloads the model + finish images, runs
the RhinoPython scripts in `rhino_scripts/` inside headless Rhino, and posts results:

| Script | What it does |
| --- | --- |
| `analyze_model.py` | imports DWG/DXF/3DM/SKP…, extracts layers, block definitions (instance references), part bounding boxes and units into the structure contract; captures a shaded viewport preview |
| `render_model.py` | creates Rhino/V-Ray materials from the finish images with **real-world texture scale** (WCS box mapping sized from each swatch's inches), assigns them by layer / part / block definition (scripted `BlockEdit` + `BlockEditSave` for block parts), sets camera + resolution and renders the frame |

## 3. Agent ↔ server contract

* `GET  /api/agent/jobs/next` — claim oldest queued job (payload includes model file URL,
  structure, and for renders: settings + assignments with finish file URLs & swatch sizes)
* `POST /api/agent/jobs/{id}/progress` — `{progress, stage}` heartbeat
* `POST /api/agent/jobs/{id}/complete` — multipart: `structure` JSON (analyze jobs) and/or
  result images (render jobs)
* `POST /api/agent/jobs/{id}/fail` — `{error}`

## Notes & TODOs

* V-Ray must be the **current renderer** in Rhino on the worker machine; the script uses
  Rhino's render pipeline which V-Ray hooks. For sample counts / denoising, bind the
  V-Ray Python API where marked `TODO(vray-py)` in `render_model.py`.
* Block parts: assignments with `target_kind=block` open the definition via `BlockEdit`,
  assign materials to definition geometry, and save — every instance updates at once,
  exactly like editing manually.
* Units: the analyze script reports Rhino's model units; the UI and texture scaling work
  in inches (convert in `render_model.py` if your drawings are metric).
