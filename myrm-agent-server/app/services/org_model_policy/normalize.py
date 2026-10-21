"""Normalize org model policy glob patterns for LiteLLM full model names.

[INPUT]
- Allowed pattern strings from control-plane sync or local config

[OUTPUT]
- Canonical glob patterns for ``provider/model`` matching

[POS]
Server-side mirror of control-plane ``model_policy_normalize`` for enforce and
frontend read paths when sandbox config predates canonical fanout.
"""

from __future__ import annotations


class OrgModelPolicyPatternError(ValueError):
    """Raised when a model policy pattern is invalid."""


def normalize_org_model_policy_pattern(pattern: str) -> str:
    """Normalize a glob pattern for LiteLLM ``provider/model`` matching."""
    trimmed = pattern.strip()
    if not trimmed:
        raise OrgModelPolicyPatternError("Pattern must not be empty")
    if trimmed == "*":
        return "*"
    if "/" in trimmed:
        return trimmed
    return f"*/{trimmed}"
