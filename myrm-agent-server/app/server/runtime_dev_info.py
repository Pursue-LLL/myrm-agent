"""Runtime listen port and dev mode — set by run.py before uvicorn starts."""

from __future__ import annotations

from typing import Literal, TypedDict

DevMode = Literal["split_dev", "standalone_webui"]

_listen_port: int = 8080
_dev_mode: DevMode = "split_dev"

WEBUI_DEV_PORT = 3000


class RuntimeDevInfo(TypedDict):
    dev_mode: DevMode
    listen_port: int
    listen_host: str
    backend_port: int
    webui_dev_port: int | None


def set_runtime_listen(*, port: int, host: str, dev_mode: DevMode) -> None:
    global _listen_port, _dev_mode
    _listen_port = port
    _dev_mode = dev_mode
    import os

    os.environ["PORT"] = str(port)
    os.environ["HOST"] = host


def get_runtime_dev_info() -> RuntimeDevInfo:
    import os

    host = os.getenv("HOST", "127.0.0.1")
    webui_dev_port = WEBUI_DEV_PORT if _dev_mode == "split_dev" else None
    return {
        "dev_mode": _dev_mode,
        "listen_port": _listen_port,
        "listen_host": host,
        "backend_port": _listen_port,
        "webui_dev_port": webui_dev_port,
    }
