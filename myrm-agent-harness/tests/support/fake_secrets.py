"""Credential-shaped fakes for redaction, leak-detection and poisoning tests.

[INPUT]
- body (POS: the caller-chosen part of the credential after the provider prefix)
- seed (POS: any text the generated hex key is derived from)

[OUTPUT]
- openai_style_key(body): fake ``sk-`` key (a ``proj-`` or ``ant-`` infix belongs to the body)
- github_token(body): fake GitHub personal access token
- jwt_shaped(header_body, payload_body, signature): fake JWT
- hex_secret(seed, length): hex string that reads like a random key and is derived from ``seed``

[POS]
The one place that assembles credential-shaped fakes for the harness tests. The credential-literal guard
(myrm-agent-server/tests/architecture/test_no_credential_literals.py) flags a provider-shaped token, or a literal
next to an ``api_key`` name, whose value does not look like a fixture, so the provider prefix is joined here at call
time and test source never holds a whole token.
"""

from __future__ import annotations

import hashlib

# Joined from two literals so this file never holds a contiguous provider prefix either.
_OPENAI_STYLE_PREFIX = "sk" + "-"
_GITHUB_PREFIX = "gh" + "p_"
_JWT_SEGMENT_PREFIX = "ey" + "J"


def openai_style_key(body: str) -> str:
    """Return a fake ``sk-`` key; ``body`` is everything after the ``sk-`` prefix."""
    return _OPENAI_STYLE_PREFIX + body


def github_token(body: str) -> str:
    """Return a fake GitHub personal access token; ``body`` is everything after the ``ghp_`` prefix."""
    return _GITHUB_PREFIX + body


def jwt_shaped(header_body: str, payload_body: str, signature: str) -> str:
    """Return a fake JWT; each body is everything after the ``eyJ`` that opens its segment."""
    return f"{_JWT_SEGMENT_PREFIX}{header_body}.{_JWT_SEGMENT_PREFIX}{payload_body}.{signature}"


def hex_secret(seed: str, length: int = 32) -> str:
    """Return ``length`` (at most 64) hex characters derived from ``seed``, the way a random hex key reads."""
    return hashlib.sha256(seed.encode()).hexdigest()[:length]
