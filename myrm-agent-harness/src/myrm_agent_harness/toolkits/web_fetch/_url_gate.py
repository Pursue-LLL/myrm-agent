"""Pre-fetch URL gate of the web fetch tool: canonical spelling, host blocklist, SSRF guard, exfiltration check.

[INPUT]
- utils.url_syntax::parse_outbound_url (POS: the one canonical spelling of an outbound URL)
- toolkits.browser.domain_filter::DomainBlocklist (POS: hostname blocklist for benchmark decontamination) [lazy]
- core.security.guards.ssrf::validate_url_for_ssrf (POS: SSRF classification of a URL) [lazy]
- utils.url_utils::check_url_exfiltration, sanitize_url_for_error (POS: secret-in-URL detection) [lazy]
- utils.errors::ToolError, ToolErrorCategory

[OUTPUT]
- validate_urls: the URLs in canonical spelling, or a ToolError naming the first URL that may not be fetched

[POS]
Runs before any request of the web fetch tool. A URL is judged in the spelling it is fetched in, so the
blocklist, the SSRF guard and the HTTP, stealth and browser tiers all read the same host.
"""

from __future__ import annotations

from myrm_agent_harness.utils.errors import ToolError, ToolErrorCategory
from myrm_agent_harness.utils.url_syntax import parse_outbound_url


def validate_urls(
    urls: list[str],
    *,
    blocked_hostnames: tuple[str, ...] | None,
    allow_private_networks: bool,
) -> list[str]:
    """Refuse URLs that the host blocklist, SSRF guard or exfiltration check does not allow, before any request.

    Returns the URLs in canonical spelling: what was judged here is what gets fetched.
    """
    targets = []
    for url in urls:
        target, error = parse_outbound_url(url)
        if target is None:
            raise ToolError(
                f"URL blocked: {error} — {url}",
                user_hint="The URL is not a valid http(s) address. Use a different URL.",
            )
        targets.append(target)
    canonical_urls = [target.url for target in targets]

    if blocked_hostnames:
        from myrm_agent_harness.toolkits.browser.domain_filter import DomainBlocklist

        blocklist = DomainBlocklist.from_strings(blocked_hostnames)
        for target in targets:
            if blocklist.is_blocked(target.hostname):
                raise ToolError(
                    f"URL blocked: {target.url}",
                    user_hint="The URL host is excluded from fetching. Use a different URL.",
                    error_code="BENCHMARK_BLOCKED_HOST",
                    diagnostic_info={
                        "error_category": ToolErrorCategory.BENCHMARK_BLOCKED.value,
                        "hostname": target.hostname,
                    },
                )

    if allow_private_networks:
        return canonical_urls

    from myrm_agent_harness.core.security.guards.ssrf import validate_url_for_ssrf
    from myrm_agent_harness.utils.logger_utils import get_agent_logger
    from myrm_agent_harness.utils.url_utils import check_url_exfiltration, sanitize_url_for_error

    for url in canonical_urls:
        verdict = validate_url_for_ssrf(url)
        if not verdict.safe:
            raise ToolError(
                f"URL blocked (SSRF protection): {verdict.error} — {url}",
                user_hint="The URL is blocked for security reasons. Use a different, publicly accessible URL.",
            )

        exfiltration_warnings = check_url_exfiltration(url, allow_private_networks=allow_private_networks)
        if exfiltration_warnings:
            logger = get_agent_logger(__name__)
            safe_url = sanitize_url_for_error(url)
            logger.warning(" Potential data exfiltration detected in URL: %s", safe_url)
            for warning in exfiltration_warnings:
                logger.warning(" - %s", warning)
            raise ToolError(
                f"URL blocked (data exfiltration detection): {'; '.join(exfiltration_warnings)} — {safe_url}",
                user_hint="The URL appears to contain sensitive data. Remove secrets from the URL.",
            )
    return canonical_urls
