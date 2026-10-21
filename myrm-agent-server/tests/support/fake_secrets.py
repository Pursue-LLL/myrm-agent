"""Provider-shaped fake credentials for redaction and leak-detection tests.

[INPUT]
- body (POS: the caller-chosen part of the credential after the provider prefix)

[OUTPUT]
- stripe_live_key(body): fake Stripe live secret key
- slack_bot_token(body): fake Slack bot token

[POS]
The one place that assembles detector-shaped fake credentials. GitHub push protection rejects any
committed text that contains a complete provider-shaped token, fake or not, so the provider prefix
is joined here at call time and test source never holds a whole token. Enforced by
tests/architecture/test_no_provider_shaped_secrets_in_tests.py.
"""

from __future__ import annotations

# Joined from two literals so this file never holds a contiguous provider prefix either.
_STRIPE_LIVE_PREFIX = "sk_" + "live_"
_SLACK_BOT_PREFIX = "xox" + "b-"


def stripe_live_key(body: str) -> str:
    """Return a fake Stripe live secret key; ``body`` is everything after the live-key prefix."""
    return _STRIPE_LIVE_PREFIX + body


def slack_bot_token(body: str) -> str:
    """Return a fake Slack bot token; ``body`` is everything after the bot-token prefix."""
    return _SLACK_BOT_PREFIX + body
