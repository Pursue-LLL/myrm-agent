"""CORS 配置和验证

提供 CORS origins 配置的解析、验证和默认配置。
"""

import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES: frozenset[str] = frozenset(["http://", "https://", "tauri://"])

CORS_ORIGINS_DEFAULT: str = (
    "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001,tauri://localhost"
)

# The desktop shell serves its WebView from a loopback Next server on its own port.
# It passes that port to the sidecar so the allowlist follows the runtime port
# instead of a fixed list that drifts when the shell changes ports.
DESKTOP_FRONTEND_PORT_ENV: str = "MYRM_DESKTOP_FRONTEND_PORT"


class CORSConfigError(Exception):
    """CORS 配置错误，当 CORS origins 配置为空或包含无效格式时抛出。"""


def parse_and_validate_cors_origins(origins_str: str) -> list[str]:
    """解析并验证 CORS origins 配置

    Args:
        origins_str: 逗号分隔的 origins 字符串

    Returns:
        解析后的 origins 列表

    Raises:
        CORSConfigError: 配置为空或包含无效格式的 origin

    Examples:
        >>> parse_and_validate_cors_origins("http://localhost:3000,http://localhost:3001")
        ['http://localhost:3000', 'http://localhost:3001']

        >>> parse_and_validate_cors_origins("http://localhost:3000, http://localhost:3001 ")
        ['http://localhost:3000', 'http://localhost:3001']
    """
    origins = [o.strip() for o in origins_str.split(",") if o.strip()]

    if not origins:
        raise CORSConfigError(
            "CORS_ORIGINS cannot be empty. "
            "Please set CORS_ORIGINS environment variable with comma-separated origins. "
            "Example: CORS_ORIGINS='http://localhost:3000,https://example.com'"
        )

    for origin in origins:
        if not any(origin.startswith(scheme) for scheme in ALLOWED_SCHEMES):
            schemes_str = ", ".join(sorted(ALLOWED_SCHEMES))
            raise CORSConfigError(
                f"Invalid CORS origin scheme in '{origin}'. "
                f"Allowed schemes: {schemes_str}. "
                "Please update CORS_ORIGINS environment variable."
            )

        parsed = urlparse(origin)
        if not parsed.netloc:
            raise CORSConfigError(
                f"Invalid CORS origin (missing host): '{origin}'. "
                "Origin must include a host, e.g., 'http://localhost:3000'. "
                "Please update CORS_ORIGINS environment variable."
            )

    logger.info(f"CORS origins configured: {len(origins)} origin(s)")
    return origins


def resolve_cors_origins(origins_str: str) -> list[str]:
    """Return the configured origins plus the desktop shell's own frontend origin.

    The WebView is served by a loopback Next server on a dedicated port. Calls that
    bypass the Next proxy (notifications SSE, direct probes) are cross-origin from
    that page, so the exact origin must be allowlisted or the browser drops them even
    though the backend is healthy. The shell passes its port through
    ``MYRM_DESKTOP_FRONTEND_PORT``; deriving the origin here keeps the allowlist in
    sync with the port the user actually runs.

    A missing or malformed port leaves the configured list untouched: the shell is
    the only producer of this variable, and a hand-edited environment must not be
    able to widen the allowlist silently.
    """
    origins = parse_and_validate_cors_origins(origins_str)
    port = _desktop_frontend_port()
    if port is None:
        return origins

    for host in ("127.0.0.1", "localhost"):
        origin = f"http://{host}:{port}"
        if origin not in origins:
            origins.append(origin)
    logger.info(
        "CORS: desktop frontend origin http://127.0.0.1:%d added to allowlist",
        port,
    )
    return origins


def _desktop_frontend_port() -> int | None:
    raw = os.environ.get(DESKTOP_FRONTEND_PORT_ENV, "").strip()
    if not raw:
        return None
    try:
        port = int(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r", DESKTOP_FRONTEND_PORT_ENV, raw)
        return None
    if not 1 <= port <= 65535:
        logger.warning("Ignoring out-of-range %s=%r", DESKTOP_FRONTEND_PORT_ENV, raw)
        return None
    return port
