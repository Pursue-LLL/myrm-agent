"""Shared Twilio utilities for SMS and Voice channels.

Provides signature verification used by both SMSChannel and VoiceCallChannel
to validate inbound webhook requests from Twilio.

[INPUT]
(no external dependencies — pure crypto utility)

[OUTPUT]
- verify_twilio_signature: validate X-Twilio-Signature header
- port_variant_url: toggle default port for signature edge case

[POS]
Internal utility module. Shared by Twilio-based channels (SMS, Voice) to avoid
duplicating signature verification logic.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import urllib.parse


def verify_twilio_signature(
    auth_token: str,
    url: str,
    params: dict[str, str],
    signature: str,
) -> bool:
    """Validate Twilio webhook request signature (HMAC-SHA1).

    Tries both the original URL and a port-variant URL, since Twilio may
    sign with either form (with/without the default port for the scheme).

    Args:
        auth_token: Twilio Auth Token used as HMAC key.
        url: Full webhook URL as Twilio sees it.
        params: POST body parameters (flat key-value dict).
        signature: Value of X-Twilio-Signature header.

    Returns:
        True if the signature is valid.
    """
    if not auth_token or not signature:
        return False

    if _check_signature(auth_token, url, params, signature):
        return True

    variant = port_variant_url(url)
    if variant and _check_signature(auth_token, variant, params, signature):
        return True

    return False


def port_variant_url(url: str) -> str | None:
    """Return the URL with the default port toggled, or None.

    Twilio's signature calculation may include or omit the default port
    (443 for https, 80 for http). This function generates the alternate
    form to try both during verification.
    """
    parsed = urllib.parse.urlparse(url)
    default_ports = {"https": 443, "http": 80}
    default_port = default_ports.get(parsed.scheme)
    if default_port is None:
        return None

    if parsed.port == default_port:
        return urllib.parse.urlunparse(
            (parsed.scheme, parsed.hostname or "", parsed.path,
             parsed.params, parsed.query, parsed.fragment)
        )
    elif parsed.port is None:
        netloc = f"{parsed.hostname}:{default_port}"
        return urllib.parse.urlunparse(
            (parsed.scheme, netloc, parsed.path,
             parsed.params, parsed.query, parsed.fragment)
        )

    return None


def _check_signature(
    auth_token: str,
    url: str,
    params: dict[str, str],
    signature: str,
) -> bool:
    """Compute and compare a single Twilio HMAC-SHA1 signature."""
    data_to_sign = url + "".join(k + v for k, v in sorted(params.items()))
    computed = hmac.new(
        auth_token.encode("utf-8"),
        data_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    expected = base64.b64encode(computed).decode("ascii")
    return hmac.compare_digest(expected, signature)
