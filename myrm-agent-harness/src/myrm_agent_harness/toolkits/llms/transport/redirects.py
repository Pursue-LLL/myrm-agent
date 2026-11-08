"""Which redirect of a model request is followed, and how one that is not followed is worded.

[INPUT]
- httpx::Response (POS: the provider's answer and the address the request was sent to)

[OUTPUT]
- MAX_REDIRECTS: the redirects one request may follow
- followed_url: the address a redirect points at when following it keeps the credential on the configured host
- shown: an address as a log line or message may carry it (no credentials, query or fragment)
- redirect_notice: the failure text of a redirect that is not followed, naming where it pointed

[POS]
A gateway in front of a model endpoint (http to https, a moved path) answers with 307 or 308, which keep the method and
the body, and the call must still arrive. The request carries the provider key in a header httpx passes to whatever host
the answer names (it removes ``Authorization`` only), so a redirect is followed only to the host that was configured and
never from https to http; neither the key nor the conversation is for any other address. A 301, 302 or 303 turns the
POST into a GET that cannot carry the call, so it is reported with the address it named, as is every redirect that is
refused.
"""

from __future__ import annotations

from typing import Final

import httpx

# A gateway needs one or two hops; more is a loop.
MAX_REDIRECTS: Final = 5
# The statuses that resend the same method and body.
_METHOD_KEEPING: Final = frozenset({307, 308})
_SCHEMES: Final = frozenset({"http", "https"})


def _target(response: httpx.Response) -> httpx.URL | None:
    """The absolute address the ``Location`` header names, ``None`` when it is empty.

    httpx has already parsed the header when it hands the answer over (an unreadable one raises there), so joining it
    to the address that was called cannot fail.
    """
    location = response.headers.get("location")
    return response.url.join(location) if location else None


def _stays_home(sent: httpx.URL, target: httpx.URL) -> bool:
    """Same host (a different port is the same machine), a web scheme, and never a step down from https."""
    return (
        target.host == sent.host and target.scheme in _SCHEMES and (sent.scheme != "https" or target.scheme == "https")
    )


def followed_url(response: httpx.Response) -> httpx.URL | None:
    """The address a method-keeping redirect points at, or ``None`` when the answer is not one to follow."""
    if response.status_code not in _METHOD_KEEPING:
        return None
    target = _target(response)
    return target if target is not None and _stays_home(response.url, target) else None


def shown(url: httpx.URL) -> str:
    """The address for a log line or a message: no user info, query or fragment, any of which may carry a token."""
    return str(url.copy_with(userinfo=b"", query=None, fragment=None))


def redirect_notice(response: httpx.Response) -> str:
    """Why a redirect ended the call."""
    target = _target(response)
    if target is None:
        return "redirected without an address the transport can use"
    return (
        f"redirected to {shown(target)} and the transport does not follow it (only a 307/308 to the same host, "
        "never from https to http); use that address as the provider's base URL"
    )
