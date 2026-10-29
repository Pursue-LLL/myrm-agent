"""Short-lived tokens binding a consolidation preview plan to its execute call.

[INPUT]
- hashlib / json / secrets / time (POS: plan fingerprint, random token and expiry)

[OUTPUT]
- issue_plan_token: fingerprint a plan (sorted-key JSON, SHA-256) and issue a 900-second token for it
- validate_plan_token: accept a token only while it is unexpired and the plan still has the issued fingerprint
- revoke_plan_token: drop a token once it has been used
- ConsolidationPlanToken: the issued token and its fingerprint

[POS]
Execute may only run the plan the user previewed: a token issued for one plan fails against any other, and the
store is process-local.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass

_TTL_SECONDS = 900
_store: dict[str, tuple[float, str]] = {}


@dataclass(frozen=True)
class ConsolidationPlanToken:
    token: str
    plan_fingerprint: str


def _fingerprint(plan: object) -> str:
    payload = json.dumps(plan, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def issue_plan_token(plan: object) -> ConsolidationPlanToken:
    fp = _fingerprint(plan)
    token = secrets.token_urlsafe(24)
    _store[token] = (time.time() + _TTL_SECONDS, fp)
    return ConsolidationPlanToken(token=token, plan_fingerprint=fp)


def validate_plan_token(token: str, plan: object) -> bool:
    entry = _store.get(token)
    if entry is None:
        return False
    expires_at, fp = entry
    if time.time() > expires_at:
        _store.pop(token, None)
        return False
    return fp == _fingerprint(plan)


def revoke_plan_token(token: str) -> None:
    _store.pop(token, None)
