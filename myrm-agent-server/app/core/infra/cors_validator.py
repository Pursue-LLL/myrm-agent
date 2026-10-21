"""CORS 配置和验证

提供 CORS origins 配置的解析、验证和默认配置。
"""

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES: frozenset[str] = frozenset(["http://", "https://", "tauri://"])

CORS_ORIGINS_DEFAULT: str = (
    "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001,tauri://localhost"
)


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
