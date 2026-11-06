"""URL 工具门面。

[OUTPUT]
URL 规范化/判断、SSRF 黑名单、scheme 校验、外泄检测、错误脱敏与 DNS pin 规则。

[POS]
`myrm_agent_harness.utils.url_utils` 的唯一入口；实现按解析/拦截/安全/DNS 拆分。
"""

from myrm_agent_harness.utils.url_utils.blocking import (
    SSRF_BLOCKED_HOSTNAMES,
    clear_dynamic_blocked_hostnames,
    is_blocked_ip,
    register_blocked_hostnames,
    unregister_blocked_hostnames,
)
from myrm_agent_harness.utils.url_utils.dns import build_host_resolver_rules, create_dns_pin_map
from myrm_agent_harness.utils.url_utils.parsing import (
    extract_domain,
    is_file_url,
    is_image_url,
    is_valid_image_url,
    normalize_url,
)
from myrm_agent_harness.utils.url_utils.security import (
    check_url_exfiltration,
    sanitize_url_for_error,
    validate_scheme_and_hostname,
)

__all__ = [
    "SSRF_BLOCKED_HOSTNAMES",
    "build_host_resolver_rules",
    "check_url_exfiltration",
    "clear_dynamic_blocked_hostnames",
    "create_dns_pin_map",
    "extract_domain",
    "is_blocked_ip",
    "is_file_url",
    "is_image_url",
    "is_valid_image_url",
    "normalize_url",
    "register_blocked_hostnames",
    "sanitize_url_for_error",
    "unregister_blocked_hostnames",
    "validate_scheme_and_hostname",
]
