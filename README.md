# FinishFlow — local Rhino 8 + V-Ray render automation

FinishFlow is a web app for uploading CAD drawings and laminate, PET or product-finish
swatches, mapping finishes by layer, block or part, and queueing renders. Its intended
renderer is the user's existing Rhino 8 and V-Ray licenses on Windows; a server can run
in WSL on the same computer. No cloud rendering service is required.

**Current status:** the UI, local job transport, synthetic tests and safety checks are
implemented. The updated Rhino/V-Ray analysis, BlockEdit and rendering scripts have
**not been tested in a real Rhino/V-Ray installation yet**. They need a supervised
first run on the licensed Windows machine; do not treat a connected-worker badge as
proof that a render or texture scale is correct.

## Features and limitations

* Upload DWG, DXF, 3DM, OBJ, STEP and other supported CAD formats. Rhino's actual
  import capabilities depend on its installed importers. The DXF parser remains an
  optional fallback; binary DWG requires Rhino for actual analysis.
* The Rhino analyzer traverses nested block definitions and their inner layers and
  sends a tessellated mesh/curve preview separately from the structure data. The viewer
  explicitly labels partial previews and bounding-box fallback; its finish textures
  are an approximation, not a V-Ray result.
* Finishes can be assigned by layer, block or individual identifiable geometry, with
  name-based suggestions and reusable pattern presets. Shared block definitions affect
  all their references; conflicting assignments are rejected. Identical overlapping
  objects can share a target. Saved presets use exact names and stable Rhino part IDs;
  edit name rules to match similar drawings. Part IDs match only the same geometry.
* Swatches carry real-world dimensions in inches. Mapping and BlockEdit are guarded
  rather than silently guessed, but their behavior still needs real Rhino/V-Ray
  verification. See [worker/README.md](worker/README.md) for important limitations,
  including rectangular swatches on multi-face objects and scaled/linked blocks.
* Real renders require an updated Rhino analysis, verified output and V-Ray worker
  manifest. A failed render is not replaced with a viewport capture or a swatch image.
  Quality uses V-Ray's current settings; app quality presets are simulation-only.
* `RENDER_RUNNER=agent` queues jobs only for the worker. The default `auto` routes to
  simulation when the worker is disconnected; `mock` always simulates. Mock/test results
  are labeled and are not V-Ray renders.

## Local development

From a checkout containing these changes, create the backend environment and start the
API (WSL terminal 1):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd backend
RENDER_RUNNER=agent ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in another WSL terminal:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://localhost:5173` on the same computer. The Vite proxy uses the local API;
browser requests remain relative. Run the Rhino worker natively on Windows as described
in [worker/README.md](worker/README.md). Windows-to-WSL localhost forwarding may need
diagnosis on the user's machine.

The API has **no authentication** and uploaded files are accessible through `/media`.
Keep it on localhost or a firewall-restricted trusted LAN; do not expose it publicly.
Runtime data lives in `backend/data/`. `backend/seed.py --fresh` **deletes existing
application data** and is not needed for normal startup.

## Tests

```bash
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
cd frontend && npm run build
```

The tests include nested-transform stand-ins, part/assignment conflict checks, API
uploads, false-success regressions and a local stub-worker transport test (on Unix).
The viewer, selection, search, scaling, presets and a simulated render were also
browser-tested with synthetic geometry. The stub produces images explicitly marked
**SIMULATED TEST**; none of these tests validates Rhino or V-Ray.

## Main directories

* `backend/app/` — FastAPI, jobs, media, assignments and simulation fallback.
* `worker/` — Windows polling agent and RhinoPython analysis/render scripts.
* `frontend/` — React, Vite and the three.js interactive preview.
* `tests/` — Rhino-independent safety, protocol and geometry-adapter tests.
