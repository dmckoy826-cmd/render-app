# Rhino / V-Ray worker

FinishFlow can run Rhino 8 and V-Ray **locally on the Windows machine that already has
the licenses**. The server may run in WSL on the same computer. No cloud rendering
service is required.

**Status: experimental.** The transport and safety checks have automated tests and a
synthetic worker test, but the Rhino scripts, BlockEdit commands, V-Ray materials,
texture scale and rendered image have **not yet been verified in a real Rhino/V-Ray
installation**. A green worker indicator is only a heartbeat, not proof that Rhino,
V-Ray, a license, geometry, materials or rendering work.

## Routing and local safety

Set `RENDER_RUNNER=agent` on the API to queue jobs exclusively for the Windows worker.
The default `auto` mode falls back to a simulated renderer when no heartbeat is present;
`mock` always uses simulation. The worker sends a heartbeat while Rhino is busy as
well as between jobs.

The API has **no authentication** and serves uploaded files under `/media`. Bind it to
localhost for a single-computer setup, or restrict it to a trusted LAN with a firewall.
Do not expose it to the public internet. Canceling a running job prevents its result
from being accepted but does not yet terminate its Rhino process.

## Connecting the Windows worker

1. Put the complete `worker/` folder on the Windows computer, including `rhino_scripts/`.
2. Install Windows Python 3.10+ and `requests`: `py -3 -m pip install requests`.
3. Edit `start_worker.bat`, or from a Windows terminal in the checkout root set:
   ```bat
   set FF_API=http://127.0.0.1:8000
   set FF_RHINO=C:\Program Files\Rhino 8\System\Rhino.exe
   py -3 worker\agent.py
   ```
   This address assumes the Windows host can reach the WSL API through localhost
   forwarding. If it cannot, diagnose WSL networking before widening the API binding.
4. If the V-Ray Python wrapper is not found automatically, set `FF_VRAY_SCRIPTS` to the
   folder containing `rhVRay.py` / `rh8VRay.py` (normally the V-Ray for Rhinoceros
   installation folder). `FF_POLL` changes the polling interval in seconds.
5. Connect the worker, then **re-analyze** existing models. Old, DXF-only or simulated
   structures cannot be used for real renders because their part identifiers are not
   compatible with the new Rhino analysis. Old part assignments may need to be cleared
   and remapped.

## First supervised validation

Watch the Windows worker console and the FinishFlow Jobs page during the first run.
Use a small copy of a drawing, not the only copy of a production file:

1. Confirm Rhino can import it without a modal dialog and has correct model units.
2. Analyze it and compare nested layers, block counts and the tessellated viewer against
   Rhino. Unsupported object types and preview size limits are explicitly marked as
   partial. Curves are shown as linework and are not assumed to be renderable surfaces.
3. Assign a square, known-size swatch to a simple surface, then to a part inside an
   embedded block. Compare the material, tile size, grain direction and every affected
   instance in Rhino/V-Ray.
4. Render at a small resolution using **current V-Ray settings**. Confirm V-Ray is the
   active renderer, the image is truly a finished V-Ray image, and its resolution and
   appearance match. Quality presets and denoising controls are not integrated yet.
5. If a job fails, inspect the error in Jobs and the Windows console. Rhino's error
   traceback is forwarded when it can be written; GUI/modal failures can still require
   inspection on Windows. Do not assume that every failure is captured perfectly.

## Targeting and current limitations

* Geometry inside nested block definitions is traversed and displayed. Targets are
  derived from geometry, definition and layer rather than Rhino's changing edit-mode
  IDs. Distinct objects can be overridden individually; coincident indistinguishable
  objects share a target and are labeled in the UI.
* BlockEdit changes the **definition**, so all references of it change. Conflicting
  assignments across shared nested definitions are rejected. To vary one instance,
  make its block definition unique in Rhino and re-analyze; automatic per-instance
  cloning is not implemented.
* Linked/reference blocks, locked/hidden block objects, scaled block instances, curve
  finish assignments, stale targets and mismatched BlockEdit copies are rejected. A
  layer/block assignment covering unsupported object types is rejected; choose supported
  parts individually instead.
* Mapping is attempted in model units using a planar projection for planar surfaces or
  square box projection otherwise. Rectangular swatches on non-planar/multi-face
  objects are rejected rather than silently stretched. Real V-Ray interpretation,
  material conversion and physical tile dimensions must still be validated locally.
  Swatches currently create basic bitmap materials; dedicated metalness/roughness and
  V-Ray material-library controls are not implemented.
* The preview is Rhino tessellation/linework, not a V-Ray render; finishes in the viewer
  are approximate. Older/mock/DXF analyses fall back to clearly labeled bounding boxes.
* The worker isolates swatches from output, requires a completed V-Ray manifest and
  correctly sized PNG, and never substitutes a viewport capture for a failed render.
  These checks cannot replace visual validation of the actual V-Ray output.

## Testing without Rhino

From the repository root:

```bash
python -m pip install -r backend/requirements-dev.txt
python -m unittest discover -s tests -v
cd frontend && npm ci && npm run build
```

`worker/stub_rhino.py` stands in for Rhino for an end-to-end transport test. Set
`FF_RHINO` to its absolute path and `FF_ALLOW_STUB=1` on the agent. Its geometry and
renders are synthetic and the API/gallery label them **SIMULATED TEST**. Never use
that flag as evidence that Rhino or V-Ray is working. The older `dev_fake_worker.py`
can test legacy analysis/protocol behavior but does not supply new Rhino targets for
real-render eligibility.
