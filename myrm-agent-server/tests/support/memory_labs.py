"""Skip a Chrome E2E node whose runtime was started without Memory Labs.

The Command Center is a Memory Labs surface. The backend mounts its routes only when ``MYRM_MEMORY_LABS`` is on and the
frontend renders its panels only when ``NEXT_PUBLIC_MEMORY_LABS`` is ``1``. Both are read when the runtime starts, so a
running node cannot turn them on; ``require_memory_labs`` names what is missing and the command that starts a complete runtime.
"""

from __future__ import annotations

import os

import pytest

from tests.support.chrome_mcp_e2e import http_json

# A Labs-only route, relative to the memory router: the backend serves it exactly when ``MYRM_MEMORY_LABS`` is on.
LABS_ONLY_ROUTE = "/command-center/consolidation/undo"

_API_PREFIX = "/api/v1"
_BACKEND_SWITCH = "MYRM_MEMORY_LABS"
_FRONTEND_SWITCH = "NEXT_PUBLIC_MEMORY_LABS"
_SCHEMA_TIMEOUT_SEC = 60.0
# ``./myrm-dev`` takes test nodes relative to the monorepo root; pytest names them relative to this directory.
_SERVER_DIR = "myrm-agent/myrm-agent-server/"


def _backend_mounts_labs(api_url: str) -> bool:
    """Read it off the OpenAPI schema: an unmounted Labs route answers 404 or 405 depending on the route beside it."""
    schema = http_json("GET", f"{api_url}/openapi.json", timeout_sec=_SCHEMA_TIMEOUT_SEC)
    paths = schema.get("paths") if isinstance(schema, dict) else None
    if not isinstance(paths, dict):
        raise RuntimeError(f"{api_url}/openapi.json carries no route table")
    methods = paths.get(f"{_API_PREFIX}/memory{LABS_ONLY_ROUTE}")
    return isinstance(methods, dict) and "get" in methods


def _launch_command() -> str:
    node = os.environ.get("PYTEST_CURRENT_TEST", "").rsplit(" (", 1)[0].removeprefix(_SERVER_DIR) or "<test node>"
    return f"{_BACKEND_SWITCH}=1 {_FRONTEND_SWITCH}=1 ./myrm-dev test -m chrome_e2e {_SERVER_DIR}{node}"


def require_memory_labs(api_url: str) -> None:
    """Skip the running node unless the runtime at ``api_url`` mounts the Labs routes and renders the Labs panels.

    The backend answers for itself through its route table. A running frontend does not report its build switch, so that
    one is read from this process's environment: the runner starts the frontend from the same shell as this process.
    """
    missing: list[str] = []
    if not _backend_mounts_labs(api_url):
        missing.append(f"the backend does not mount the Labs routes ({_BACKEND_SWITCH} is off)")
    if os.environ.get(_FRONTEND_SWITCH) != "1":
        missing.append(f"the frontend does not render the Labs panels ({_FRONTEND_SWITCH} is not 1)")
    if missing:
        reason = f"Memory Labs is off in this runtime: {'; '.join(missing)}. Run: {_launch_command()}"
        # The E2E runner reports skips by count only, so the reason is also written to its log.
        print(f"E2E_MEMORY_LABS_OFF: {reason}", flush=True)
        pytest.skip(reason)
