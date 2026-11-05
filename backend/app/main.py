"""FinishFlow API — FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import agentstate, config
from .db import Base, engine
from .routers import agent, finishes, jobs, models, presets, renders


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="FinishFlow API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/media", StaticFiles(directory=str(config.MEDIA_DIR)), name="media")

app.include_router(finishes.router)
app.include_router(models.router)
app.include_router(jobs.router)
app.include_router(presets.router)
app.include_router(renders.router)
app.include_router(agent.router)


@app.get("/api/system/info")
def system_info():
    st = agentstate.snapshot()
    mode = config.RUNNER
    if mode == "agent":
        runner_active = "agent"
        label = "Rhino worker agent (V-Ray for Rhino)"
    elif mode == "auto":
        runner_active = "agent" if st["agent_connected"] else "mock"
        label = ("Rhino worker connected — jobs run on your machine"
                 if st["agent_connected"] else
                 "Simulated engine — no Rhino worker connected (jobs queue for it in agent mode)")
    else:
        runner_active = "mock"
        label = "Simulated engine (mock Rhino/V-Ray)"
    return {
        "runner": runner_active,
        "mode": mode,
        "engine_label": label,
        **st,
        "version": app.version,
        "target": "Rhino 8 + V-Ray 7 · LAN deployment",
    }


@app.get("/api/system/pick-folder")
def pick_folder():
    import os
    import subprocess
    if os.name != "nt":
        return {"path": ""}
    ps_script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$f.Description = 'Select output folder for SKU batch renders'; "
        "$f.ShowNewFolderButton = $true; "
        "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.SelectedPath }"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Sta", "-Command", ps_script],
            capture_output=True, text=True, timeout=120,
        )
        return {"path": (proc.stdout or "").strip()}
    except Exception:
        return {"path": ""}


@app.get("/api/system/pick-file")
def pick_file():
    import os
    import subprocess
    if os.name != "nt":
        return {"path": ""}
    ps_script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$f = New-Object System.Windows.Forms.OpenFileDialog; "
        "$f.Title = 'Select CAD / Rhino Model'; "
        "$f.Filter = 'CAD & 3D Models (*.3dm;*.dwg;*.dxf;*.step;*.stp;*.obj;*.skp)|*.3dm;*.dwg;*.dxf;*.step;*.stp;*.obj;*.skp|All Files (*.*)|*.*'; "
        "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.FileName }"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Sta", "-Command", ps_script],
            capture_output=True, text=True, timeout=120,
        )
        return {"path": (proc.stdout or "").strip()}
    except Exception:
        return {"path": ""}


@app.get("/api/health")
def health():
    return {"ok": True}
