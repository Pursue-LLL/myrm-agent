"""Best-effort SearXNG bootstrap for local / WebUI modes (non-blocking)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_FILE = _SERVER_ROOT / "docker-compose.yaml"


def try_start_local_search_profile(*, blocking: bool = False) -> bool:
    """Start SearXNG via docker compose search profile when Docker is available.

    Returns True if compose was invoked (not necessarily that containers are healthy yet).
    """
    if not shutil.which("docker"):
        logger.info(
            "Docker not available — skipping SearXNG auto-start (install Docker or configure search in Settings)",
        )
        return False

    if not _COMPOSE_FILE.is_file():
        logger.warning("docker-compose.yaml not found at %s — skip SearXNG auto-start", _COMPOSE_FILE)
        return False

    cmd = [
        "docker",
        "compose",
        "-f",
        str(_COMPOSE_FILE),
        "--profile",
        "search",
        "up",
        "-d",
    ]
    try:
        subprocess.run(
            cmd,
            cwd=_SERVER_ROOT,
            check=False,
            timeout=120 if blocking else None,
            capture_output=not blocking,
        )
        logger.info("SearXNG profile start requested (http://127.0.0.1:8081 when ready)")
        return True
    except subprocess.TimeoutExpired:
        logger.warning("SearXNG docker compose timed out")
        return False
    except OSError as exc:
        logger.warning("Could not start SearXNG profile: %s", exc)
        return False
