"""Process-local revision counter for org model policy sync events.

[INPUT]
- org_model_policy_sync POST handler bumps revision after CP push

[OUTPUT]
- get_org_model_policy_revision / bump_org_model_policy_revision

[POS]
Server business layer. Gives execution_cache fingerprint a sync-safe signal
without async ConfigService reads during fingerprint hashing.
"""

from __future__ import annotations

_org_model_policy_revision: int = 0


def get_org_model_policy_revision() -> int:
    return _org_model_policy_revision


def bump_org_model_policy_revision() -> int:
    global _org_model_policy_revision
    _org_model_policy_revision += 1
    return _org_model_policy_revision
