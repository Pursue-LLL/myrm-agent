"""Default ports of the stacks the dev tooling talks to (SSOT, mirrored by dev_state_paths.sh).

Three kinds of runtime must never compete for a port:

* the user's own stack (``myrm start``, namespace ``user``) and the desktop sidecar keep the
  product defaults 8080 / 3000;
* the shared dev stack (``./myrm-dev``, namespace ``shared``) lives on the disjoint ports below;
* isolated runtimes are allocated from their own ranges by ``isolated_runtime.allocator``.

"The shared stack" is also a *sentinel* the tooling compares URLs against ("is this the shared
API, or a private one?"), so every such comparison goes through the helpers here instead of a
literal. ``MYRM_SHARED_BACKEND_PORT`` / ``MYRM_SHARED_FRONTEND_PORT`` override the defaults.

stdlib only; ``scripts/dev/tests/test_dev_ports_contract.py`` pins parity with the bash and mjs mirrors.

[INPUT]
- Process environment (POS: runtime namespace and port overrides exported by the launchers): MYRM_RUNTIME_NAMESPACE, MYRM_SHARED_BACKEND_PORT, MYRM_SHARED_FRONTEND_PORT, MYRM_BACKEND_PORT

[OUTPUT]
- shared_backend_port / shared_frontend_port / shared_api_base / shared_ui_base: ports and loopback bases of the shared dev stack
- default_backend_port / default_frontend_port / current_backend_port / current_api_base: namespace-aware defaults (user -> 8080 / 3000, anything else -> shared)
- is_shared_api_base: sentinel check for "is this URL the shared API"
- cors_origins: CORS_ORIGINS for a backend whose UI is not on a product port (CLI: ``dev_ports.py cors-origins --ui-port N``)

[POS]
Default ports of the user, shared dev and isolated stacks — SSOT; mirrored by dev_state_paths.sh and dev-ports.mjs.
"""

from __future__ import annotations

import argparse
import os
from typing import Final

USER_BACKEND_PORT: Final = 8080
USER_FRONTEND_PORT: Final = 3000
SHARED_BACKEND_PORT: Final = 28080
SHARED_FRONTEND_PORT: Final = 23000

USER_RUNTIME_NAMESPACE: Final = "user"
LOOPBACK: Final = "127.0.0.1"

# Origins the backend accepts when ``CORS_ORIGINS`` is unset (app/core/infra/cors_validator.py).
PRODUCT_CORS_ORIGINS: Final = (
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "tauri://localhost",
)


def _port_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw.isdigit() else default


def is_user_runtime() -> bool:
    return os.environ.get("MYRM_RUNTIME_NAMESPACE", "").strip() == USER_RUNTIME_NAMESPACE


def shared_backend_port() -> int:
    return _port_from_env("MYRM_SHARED_BACKEND_PORT", SHARED_BACKEND_PORT)


def shared_frontend_port() -> int:
    return _port_from_env("MYRM_SHARED_FRONTEND_PORT", SHARED_FRONTEND_PORT)


def shared_api_base() -> str:
    return f"http://{LOOPBACK}:{shared_backend_port()}"


def shared_ui_base() -> str:
    return f"http://{LOOPBACK}:{shared_frontend_port()}"


def default_backend_port() -> int:
    """Port of the current runtime's backend when no ``MYRM_BACKEND_PORT`` is exported."""
    return USER_BACKEND_PORT if is_user_runtime() else shared_backend_port()


def default_frontend_port() -> int:
    return USER_FRONTEND_PORT if is_user_runtime() else shared_frontend_port()


def current_backend_port() -> int:
    """The backend port this process was told to use, else the namespace default."""
    return _port_from_env("MYRM_BACKEND_PORT", default_backend_port())


def current_api_base() -> str:
    return f"http://{LOOPBACK}:{current_backend_port()}"


def is_shared_api_base(api_base: str) -> bool:
    """True when ``api_base`` points at the shared dev API (the sentinel the tooling compares to)."""
    return api_base.strip().rstrip("/") == shared_api_base()


def cors_origins(*ui_ports: int) -> str:
    """``CORS_ORIGINS`` value: the product origins plus the loopback origin of every UI port.

    The backend only accepts a control-plane request whose ``Origin`` is allow-listed, and the
    Next dev server forwards the browser's origin, so a UI on a non-product port must be listed.
    """
    origins = list(PRODUCT_CORS_ORIGINS)
    for port in ui_ports:
        for host in (LOOPBACK, "localhost"):
            origin = f"http://{host}:{port}"
            if origin not in origins:
                origins.append(origin)
    return ",".join(origins)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dev stack port SSOT")
    sub = parser.add_subparsers(dest="command", required=True)
    cors = sub.add_parser("cors-origins", help="print the CORS_ORIGINS value for the given UI ports")
    cors.add_argument("--ui-port", type=int, action="append", default=[])
    args = parser.parse_args(argv)
    print(cors_origins(*args.ui_port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
