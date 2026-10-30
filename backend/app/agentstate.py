"""Live state of the Rhino worker agent (heartbeat tracking).

Every GET /api/agent/jobs/next poll and every progress/complete/fail POST counts as a
heartbeat. In RENDER_RUNNER=auto mode the server routes new jobs to the agent while it
is connected and falls back to the built-in simulation engine otherwise.
"""
from __future__ import annotations

import os
import threading
import time

# A worker polling every ~3-5 s is considered connected for this long after its last
# heartbeat (generous enough to survive brief network hiccups / server restarts).
CONNECTED_WINDOW_S = float(os.environ.get("RENDER_AGENT_WINDOW", "90"))

_lock = threading.Lock()
_last_poll = 0.0
_agent_name = ""


def ping(name: str = "") -> None:
    global _last_poll, _agent_name
    with _lock:
        _last_poll = time.time()
        if name:
            _agent_name = str(name)[:120]


def connected() -> bool:
    with _lock:
        return bool(_last_poll) and (time.time() - _last_poll) <= CONNECTED_WINDOW_S


def seconds_since_poll() -> float | None:
    with _lock:
        if not _last_poll:
            return None
        return round(time.time() - _last_poll, 1)


def snapshot() -> dict:
    with _lock:
        last = round(time.time() - _last_poll, 1) if _last_poll else None
        return {
            "agent_connected": bool(_last_poll) and (time.time() - _last_poll) <= CONNECTED_WINDOW_S,
            "agent_name": _agent_name,
            "agent_last_seen_s": last,
        }
