"""FinishFlow API — FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
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
    return {
        "runner": config.RUNNER,
        "engine_label": ("Simulated engine (mock Rhino/V-Ray)" if config.RUNNER == "mock"
                         else "Rhino worker agent (V-Ray for Rhino)"),
        "agent_connected": config.RUNNER == "agent",
        "version": app.version,
        "target": "Rhino 8 + V-Ray 7 · LAN deployment",
    }


@app.get("/api/health")
def health():
    return {"ok": True}
