"""[INPUT]
- .common (POS: shared constants and error type)

[OUTPUT]
- find_available_port, _wait_for_health

[POS]
Frontend launcher: port selection and health probing.
"""

from __future__ import annotations

import socket
import time
from urllib.error import URLError
from urllib.request import urlopen

from .common import (
    _HEALTH_CHECK_INTERVAL,
    _HEALTH_CHECK_TIMEOUT,
)


def find_available_port(preferred: int, host: str = "127.0.0.1") -> int:
    """Find an available port, preferring the given one.

    Args:
        preferred: Preferred port number.
        host: Host to bind to.

    Returns:
        Available port number.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, preferred))
            return preferred
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, 0))
            addr = s.getsockname()
            return int(addr[1])


def _wait_for_health(url: str, timeout: float = _HEALTH_CHECK_TIMEOUT) -> bool:
    """Poll a URL until it returns 200 or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as resp:  # noqa: S310
                if resp.status == 200:
                    return True
        except (URLError, OSError, TimeoutError):
            pass
        time.sleep(_HEALTH_CHECK_INTERVAL)
    return False
