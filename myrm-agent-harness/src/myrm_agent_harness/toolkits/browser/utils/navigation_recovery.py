"""Recovery suggestions for a failed browser navigation.

[INPUT]
- (none — self-contained mapping from failure facts to advice)

[OUTPUT]
- navigation_recovery_suggestions(): ordered recovery steps for an HTTP status and/or Chromium ``net::ERR_*`` text

[POS]
Turns the failure facts of a navigation (HTTP status, Chromium error text) into the next steps the Agent is shown.
``BrowserNavigationError`` calls it once at construction, so the advice travels with the exception into
``format_for_llm``. The advice speaks to the Agent only: a rejected certificate is reported to the user and never
worked around, and nothing here names the operator setting that relaxes certificate checks.
"""

from __future__ import annotations


def navigation_recovery_suggestions(status_code: int | None, error_text: str | None) -> list[str]:
    """Recovery suggestions for a failed navigation; a generic set when neither fact is recognized."""
    suggestions: list[str] = []

    if status_code:
        if status_code == 404:
            suggestions.extend(
                [
                    "URL not found - verify the URL is correct",
                    "Check if the page has moved (try searching for the content)",
                    "Try navigating to the site's homepage first",
                ]
            )
        elif status_code == 403:
            suggestions.extend(
                [
                    "Access forbidden - the site may require authentication",
                    "Try logging in first if credentials are available",
                    "Check if the site blocks automated browsers (may need stealth mode)",
                ]
            )
        elif status_code == 500:
            suggestions.extend(
                [
                    "Server error - the site may be temporarily down",
                    "Wait a few seconds and retry",
                    "Try a different page on the same site to verify server status",
                ]
            )
        elif status_code >= 400:
            suggestions.append(f"HTTP {status_code} error - check the URL and server status")

    if error_text:
        if "net::ERR_NAME_NOT_RESOLVED" in error_text:
            suggestions.extend(
                [
                    "DNS resolution failed - check the domain name",
                    "Verify internet connectivity",
                    "Try a well-known site (e.g., google.com) to test connectivity",
                ]
            )
        elif "net::ERR_CONNECTION_REFUSED" in error_text:
            suggestions.extend(
                [
                    "Connection refused - the server may be down or unreachable",
                    "Check if the port is correct (HTTP uses 80, HTTPS uses 443)",
                    "Verify the URL scheme (http:// vs https://)",
                ]
            )
        elif "net::ERR_TIMED_OUT" in error_text:
            suggestions.extend(
                [
                    "Connection timed out - the server may be slow or unreachable",
                    "Increase navigation timeout and retry",
                    "Check if the site is accessible from your network",
                ]
            )
        elif "net::ERR_SOCKS_CONNECTION_FAILED" in error_text:
            # The egress guard answers every connection it will not make this way: the browser cannot tell a refusal
            # from an unresolvable or unreachable host.
            suggestions.extend(
                [
                    "The network policy refused the connection - only public internet hosts are reachable, so "
                    "localhost, private network addresses and cloud metadata hosts are blocked",
                    "If the host should be public, check that the domain exists and resolves to a public address",
                    "Content on a private network cannot be opened from this environment",
                ]
            )
        elif "net::ERR_CERT_" in error_text:
            # The browser refuses a certificate it cannot verify (untrusted issuer, expired, other host name).
            suggestions.extend(
                [
                    "The site's security certificate was rejected (untrusted issuer, expired, or issued for a "
                    "different host name), so the page was not opened: the connection cannot be verified as the "
                    "site's own",
                    "Check that the host name in the URL is exactly the site's own address (not an IP address, an "
                    "alias or a typo) and try that address",
                    "If the certificate error persists, report it to the user as a certificate problem of the site "
                    "instead of looking for a way around the check",
                ]
            )

    if not suggestions:
        suggestions.extend(
            [
                "Verify the URL is correct and accessible",
                "Check browser console for detailed error messages",
                "Try navigating to a simpler page to isolate the issue",
            ]
        )

    return suggestions
