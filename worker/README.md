# Rhino / V-Ray worker

This folder turns the **simulated** render engine into a **real** one by driving your
licensed Rhino 8 + V-Ray installation on a Windows machine.

```
browser  →  FinishFlow server (FastAPI)  ⇄  worker/agent.py  →  Rhino 8 + V-Ray
                     job queue               polls /api/agent/*     └─ render → gallery
```

## How routing works (auto mode)

The server defaults to `RENDER_RUNNER=auto`:

* **While the agent is polling** (every poll is a heartbeat; the server considers the
  worker connected for 90 s after the last beat), analyze + render jobs are routed to
  your machine. The sidebar shows a pulsing green **"Rhino worker connected"** chip with
  the machine's hostname.
* **With no worker connected**, jobs fall back to the built-in simulated engine so the
  UI keeps working (results are watermarked/labeled SIM).
* `RENDER_RUNNER=agent` forces jobs to wait for a real worker only; `mock` forces
  simulation only.

## Quickstart (Windows machine with Rhino 8 + V-Ray)

1. Get this folder onto the machine (clone the repo, or copy `worker/`).
2. Open `start_worker.bat`, set the two values:
   ```bat
   set FF_API=http://<server-lan-ip>:8000
   set FF_RHINO=C:\Program Files\Rhino 8\System\Rhino.exe
   ```
3. Double-click `start_worker.bat` (installs `requests` if needed, then starts polling).
4. Watch the FinishFlow sidebar flip to green **"Rhino worker connected"**.
5. Upload a model or hit **Re-analyze** — the job now runs through real Rhino.

Manual equivalent: `pip install requests`, set the two env vars, `python agent.py`.

Optional env vars: `FF_POLL` (poll seconds, default 3).

### Connecting to a hosted/dev server

`FF_API` is just a base URL — it also works over HTTPS against a hosted instance
(e.g. the Arena preview URL of port 8000) as long as the worker machine can reach it.

## First supervised run — checklist

The server side of this protocol is fully tested (see dev tools below), but the
Rhino-side scripts have never touched a real Rhino install, so do the first run
watching the worker console:

1. **V-Ray is the current renderer** in Rhino (Render panel → Current Renderer → V-Ray).
   The scripts call Rhino's standard `-Render`, which invokes whatever renderer is
   current. Explicit V-Ray Python API control (sample counts per quality tier,
   denoising) is marked `TODO(vray-py)` in `render_model.py`.
2. **Analyze a small DWG/DXF first** — confirm the model page flips to the emerald
   **RHINO · true geometry** badge and the layers/blocks match your drawing.
3. **Run a draft render** — confirm the image lands in the gallery.
4. If a job fails, the **exact Rhino console output** is posted back and shown on the
   Jobs page (and in `worker` console) — no silent failures.

Anything that misbehaves on your Rhino build (command macro names can vary slightly
between builds) is a one-line fix in `rhino_scripts/` — the transport around it is
proven.

## What the scripts do

| Script | What it does |
| --- | --- |
| `analyze_model.py` | imports DWG/DXF/3DM/SKP/OBJ/STEP… via Rhino's own importers; block instances become parts with `requires_block_edit=true`; solids/surfaces/meshes become parts; 2D linework is grouped per layer; **all coordinates converted to inches** (`RhinoMath.UnitScale`); writes the structure JSON + a shaded viewport capture |
| `render_model.py` | downloads finish images from the server; creates materials with `SetBitmapTexture` and real-world texture repeat derived from each swatch's inch size vs. object bbox; assigns by **layer / part / block definition** — block targets use the scripted BlockEdit flow (`_-BlockEdit` → assign → `_-BlockEdit _SaveAndClose`, the documented scriptable options) so every instance updates at once; sizes the viewport to the requested output, renders, saves the frame |

The agent launches Rhino with the McNeel-documented pattern for script paths with
spaces — `/nosplash /notemplate /runscript="-_RunPythonScript (C:\path\script.py) _Exit"`
— and each script clears the document's Modified flag so `_Exit` can't block on a save
prompt.

## Agent ↔ server contract

* `GET  /api/agent/jobs/next?name=<host>` — claim oldest queued job (also the heartbeat;
  payload includes model file URL, structure, and for renders: settings + assignments
  with finish file URLs & swatch sizes in inches)
* `POST /api/agent/jobs/{id}/progress` — `{progress, stage}`
* `POST /api/agent/jobs/{id}/complete` — multipart: `structure` JSON + preview image
  (analyze jobs) or result images (render jobs); analyze previews from Rhino are kept
  as-is (not regenerated)
* `POST /api/agent/jobs/{id}/fail` — `{error}` → shown verbatim on the Jobs page

## Dev tools (no Rhino required)

* `dev_fake_worker.py` — speaks the exact agent protocol and completes jobs with
  generated structures/images. Use it to test the server side on any machine:
  `FF_API=http://localhost:8000 python dev_fake_worker.py`
* `stub_rhino.py` — stands in for `Rhino.exe` so you can test **agent.py's real
  transport** (downloads, subprocess launch, multipart uploads, failure reporting)
  on Linux/macOS: `FF_RHINO=/path/to/stub_rhino.py python agent.py`

Both label their output `dev-fake-worker` / `stub-rhino` so results are never
mistaken for real Rhino/V-Ray output.
