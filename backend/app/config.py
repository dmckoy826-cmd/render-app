"""Application configuration: paths and runtime settings."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
DATA_DIR = Path(os.environ.get("RENDER_DATA_DIR", str(BASE_DIR / "data")))

MEDIA_DIR = DATA_DIR / "media"
FINISH_DIR = MEDIA_DIR / "finishes"
THUMB_DIR = MEDIA_DIR / "thumbs"
MODEL_DIR = MEDIA_DIR / "models"
PREVIEW_DIR = MEDIA_DIR / "previews"
RENDER_DIR = MEDIA_DIR / "renders"
DB_PATH = DATA_DIR / "app.db"

# "mock"  -> built-in simulated Rhino/V-Ray engine (no Windows machine needed)
# "agent" -> jobs always wait in the queue for the Rhino worker agent (worker/agent.py)
# "auto"  -> route jobs to the Rhino worker while it is connected (heartbeat via
#            /api/agent/*), otherwise fall back to the simulated engine. Default.
RUNNER = os.environ.get("RENDER_RUNNER", "auto")

for _d in (FINISH_DIR, THUMB_DIR, MODEL_DIR, PREVIEW_DIR, RENDER_DIR):
    _d.mkdir(parents=True, exist_ok=True)
