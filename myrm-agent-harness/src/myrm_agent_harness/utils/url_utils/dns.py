"""[INPUT]
- myrm_agent_harness.utils.url_utils.blocking::_SSRFResultLike (POS: url_utils 子包的一部分；由 __init__.py 聚合导出。)

[OUTPUT]
- create_dns_pin_map
- build_host_resolver_rules

[POS]
把已校验的 SSRF 结果转成 hostname→IP 映射与 resolver 规则，供请求层钉扎。
"""

from __future__ import annotations

import logging

from .blocking import _SSRFResultLike

logger = logging.getLogger(__name__)


# ============================================================================
# URL 标准化和清理
# ============================================================================


def create_dns_pin_map(
    results: list[_SSRFResultLike],
) -> tuple[dict[str, str], str | None]:
    """Build hostname→IP mapping from validated SSRFResults for DNS pinning.

    Returns:
        (pin_map, error) — pin_map is ``{"hostname": "resolved_ip"}``.
        If any result is unsafe, returns ({}, error_str).
    """
    pin_map: dict[str, str] = {}
    for r in results:
        if not r.safe:
            return {}, r.error
        if r.hostname and r.resolved_ips:
            pin_map[r.hostname] = r.resolved_ips[0]
    return pin_map, None


def build_host_resolver_rules(results: list[_SSRFResultLike]) -> str:
    """Build Chrome ``--host-resolver-rules`` flag value from SSRFResults.

    Used by crawl4ai/Playwright to pin DNS at the browser level.

    Example output: ``"MAP example.com 93.184.216.34, MAP api.co 1.2.3.4"``
    """
    rules: list[str] = []
    for r in results:
        if r.safe and r.hostname and r.resolved_ips:
            rules.append(f"MAP {r.hostname} {r.resolved_ips[0]}")
    return ", ".join(rules)
