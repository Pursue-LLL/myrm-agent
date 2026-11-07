"""[INPUT]
- pathlib.Path (POS: 路径推导)

[OUTPUT]
- logger, path/version/threshold constants, _resolve_standalone_* and FrontendEnvironmentError

[POS]
Frontend launcher shared primitives.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


_FRONTEND_DIR = _PROJECT_ROOT.parent / "myrm-agent-frontend"


_STANDALONE_DIR = _FRONTEND_DIR / ".next" / "standalone"


_STANDALONE_SERVER = _STANDALONE_DIR / "server.js"


_MIN_NODE_VERSION = 18


_MAX_RESTART_ATTEMPTS = 3


_HEALTH_CHECK_TIMEOUT = 30


_HEALTH_CHECK_INTERVAL = 0.5


_TOXIC_NODE_ENV_VARS = (
    "NODE_OPTIONS",
    "NODE_PATH",
    "NODE_TLS_REJECT_UNAUTHORIZED",
    "NODE_EXTRA_CA_CERTS",
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "SSLKEYLOGFILE",
)


def _resolve_standalone_dir() -> Path:
    """Resolve the directory containing server.js in .next/standalone.

    In a monorepo setup with outputFileTracingRoot, Next.js generates
    .next/standalone/myrm-agent-frontend/server.js. In flat setups, it generates
    .next/standalone/server.js.
    """
    nested = _FRONTEND_DIR / ".next" / "standalone" / "myrm-agent-frontend"
    if (nested / "server.js").is_file():
        return nested
    flat = _FRONTEND_DIR / ".next" / "standalone"
    if (flat / "server.js").is_file():
        return flat
    return nested if nested.is_dir() else flat


def _resolve_standalone_server() -> Path:
    """Return path to server.js in resolved standalone directory."""
    return _resolve_standalone_dir() / "server.js"


class FrontendEnvironmentError(RuntimeError):
    """Raised when the frontend environment is not ready."""
