"""Production-grade default stream rules for TTSR zero-tax engine.

Enforces critical security boundaries against catastrophic deletions and credential leakages.
"""

from __future__ import annotations

import re

from myrm_agent_harness.agent.streaming.rules.types import StreamRule


def get_default_stream_rules() -> list[StreamRule]:
    """Return default suite of zero-tax dormant stream rules."""
    return [
        StreamRule(
            rule_id="ban_destructive_rm",
            name="Ban Destructive Rm",
            pattern=re.compile(
                r"(?:^|\s|;|&&|\|\|)rm\s+-[rRfF]{1,3}\s+(?:/|~|\$HOME|\.\./|\*)"
            ),
            target="all",
            reminder=(
                "Destructive recursive deletion targeting root, home, or wildcards is strictly prohibited. "
                "Please use explicit file paths or safer alternatives (e.g. moving to trash)."
            ),
            repeat_gap=10,
            action="abort_and_retry",
        ),
        StreamRule(
            rule_id="ban_private_key_leak",
            name="Ban Private Key Leak",
            pattern=re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
            target="assistant",
            reminder=(
                "Detected private key material in model output. Private cryptographic keys must never "
                "be exposed in user responses or logs."
            ),
            repeat_gap=10,
            action="abort_and_retry",
        ),
        StreamRule(
            rule_id="ban_api_credential_leak",
            name="Ban API Credential Leak",
            pattern=re.compile(r"(?:sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36,})"),
            target="all",
            reminder=(
                "Detected raw API key or token in stream output. Sanitize credentials or use environment "
                "variable references instead."
            ),
            repeat_gap=10,
            action="abort_and_retry",
        ),
    ]
