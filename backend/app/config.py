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
GEOMETRY_DIR = MEDIA_DIR / "geometry"
RENDER_DIR = MEDIA_DIR / "renders"
DB_PATH = DATA_DIR / "app.db"

# "mock"  -> built-in simulated Rhino/V-Ray engine (no Windows machine needed)
# "agent" -> jobs always wait in the queue for the Rhino worker agent (worker/agent.py)
# "auto"  -> route jobs to the Rhino worker while it is connected (heartbeat via
#            /api/agent/*), otherwise fall back to the simulated engine. Default.
RUNNER = os.environ.get("RENDER_RUNNER", "auto")

for _d in (FINISH_DIR, THUMB_DIR, MODEL_DIR, PREVIEW_DIR, GEOMETRY_DIR, RENDER_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def geometry_file_from_url(url: str) -> Path | None:
    """Resolve only server-owned geometry filenames, never arbitrary media paths."""
    prefix = "/media/geometry/"
    if not isinstance(url, str) or not url.startswith(prefix):
        return None
    name = url[len(prefix):]
    if not name or "/" in name or "\\" in name or name in (".", "..") or not name.endswith(".json"):
        return None
    return GEOMETRY_DIR / name
