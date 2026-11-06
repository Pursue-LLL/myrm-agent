"""阻止命令通过 URL 向外泄露数据。

[POS]
bash 预检子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
import re

from myrm_agent_harness.core.security.redact import command_preview

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# URL Exfiltration Detection
# ---------------------------------------------------------------------------

_URL_EXTRACTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r'curl\s+[^|;&]*?(https?://[^\s\'"]+)',
        r'wget\s+[^|;&]*?(https?://[^\s\'"]+)',
        r'fetch\s+[^|;&]*?(https?://[^\s\'"]+)',
        r'http-get\s+[^|;&]*?(https?://[^\s\'"]+)',
        r'(https?://[^\s\'"]+)',
    ]
)


def check_command_url_exfiltration(command: str) -> None:
    """Block commands containing URLs with sensitive data (API keys, credentials).

    Raises:
        ToolError: If URL contains data exfiltration patterns.
    """
    from myrm_agent_harness.utils.errors import ToolError
    from myrm_agent_harness.utils.url_utils import check_url_exfiltration, sanitize_url_for_error

    detected_urls: list[str] = []
    for pattern in _URL_EXTRACTION_PATTERNS:
        detected_urls.extend(pattern.findall(command))

    for url in set(detected_urls):
        warnings = check_url_exfiltration(url, allow_private_networks=True)
        if warnings:
            safe_url = sanitize_url_for_error(url)
            logger.warning(f" Data exfiltration detected in bash command: {command_preview(command, 100)}")
            for warning in warnings:
                logger.warning(f" - {warning} in URL: {safe_url}")
            raise ToolError(
                f"Command blocked (data exfiltration): {'; '.join(warnings)} — URL: {safe_url}",
                user_hint="The command contains a URL with sensitive data (API keys, file paths, or credentials). Remove sensitive data from the URL.",
            )
