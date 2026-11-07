"""Provider-shaped fake credentials for redaction and leak-detection tests.

[INPUT]
- body (POS: the caller-chosen part of the credential after the provider prefix)

[OUTPUT]
- stripe_live_key(body): fake Stripe live secret key
- slack_bot_token(body): fake Slack bot token
- openai_style_key(body): fake ``sk-`` key (a ``proj-`` or ``ant-`` infix belongs to the body)
- github_token(body): fake GitHub personal access token
- aws_access_key_id(body): fake AWS access key id
- gitlab_token(body): fake GitLab personal access token
- jwt_shaped(header_body, payload_body, signature): fake JWT

[POS]
The one place that assembles detector-shaped fake credentials. GitHub push protection rejects any
committed text that contains a complete provider-shaped token, fake or not, and
tests/architecture/test_no_credential_literals.py flags one whose value does not look like a fixture, so
the provider prefix is joined here at call time and test source never holds a whole token. Enforced by
tests/architecture/test_no_provider_shaped_secrets_in_tests.py (Stripe, Slack) and the credential-literal
guard (the other shapes).
"""

from __future__ import annotations

# Joined from two literals so this file never holds a contiguous provider prefix either.
_STRIPE_LIVE_PREFIX = "sk_" + "live_"
_SLACK_BOT_PREFIX = "xox" + "b-"
_OPENAI_STYLE_PREFIX = "sk" + "-"
_GITHUB_PREFIX = "gh" + "p_"
_AWS_ACCESS_KEY_PREFIX = "AK" + "IA"
_GITLAB_PREFIX = "gl" + "pat-"
_JWT_SEGMENT_PREFIX = "ey" + "J"


def stripe_live_key(body: str) -> str:
    """Return a fake Stripe live secret key; ``body`` is everything after the live-key prefix."""
    return _STRIPE_LIVE_PREFIX + body


def slack_bot_token(body: str) -> str:
    """Return a fake Slack bot token; ``body`` is everything after the bot-token prefix."""
    return _SLACK_BOT_PREFIX + body


def openai_style_key(body: str) -> str:
    """Return a fake ``sk-`` key; ``body`` is everything after the ``sk-`` prefix."""
    return _OPENAI_STYLE_PREFIX + body


def github_token(body: str) -> str:
    """Return a fake GitHub personal access token; ``body`` is everything after the ``ghp_`` prefix."""
    return _GITHUB_PREFIX + body


def aws_access_key_id(body: str) -> str:
    """Return a fake AWS access key id; ``body`` is everything after the ``AKIA`` prefix."""
    return _AWS_ACCESS_KEY_PREFIX + body


def gitlab_token(body: str) -> str:
    """Return a fake GitLab personal access token; ``body`` is everything after the ``glpat-`` prefix."""
    return _GITLAB_PREFIX + body


def jwt_shaped(header_body: str, payload_body: str, signature: str) -> str:
    """Return a fake JWT; each body is everything after the ``eyJ`` that opens its segment."""
    return f"{_JWT_SEGMENT_PREFIX}{header_body}.{_JWT_SEGMENT_PREFIX}{payload_body}.{signature}"
