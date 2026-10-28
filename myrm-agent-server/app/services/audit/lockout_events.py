"""Surface brute-force lockouts in the server log and the auth audit trail.

[INPUT]
- app.middleware.auth_audit (POS: auth audit JSONL writer, ``RATE_LIMIT_EXCEEDED`` event type)
- app.platform_utils.deployment_capabilities (POS: whether this deployment keeps an auth audit trail)
- app.core.security.share.share_hmac::token_fingerprint (POS: non-reversible share token id)

[OUTPUT]
- report_lockout: record that a client was just locked out of a credential check
- report_share_lockout: the same for a share password gate

[POS]
A lockout stops a guessing run but, left silent, tells the owner nothing about it. Each lockout is reported once, at
the moment the lock engages (never per refused attempt, so an attack cannot flood the log): always as a WARNING, and
as a ``rate_limit_exceeded`` auth audit event where the deployment audits auth (sandbox and remote WebUI; local
loopback has no one to read it). Only the client address, the guarded scope and a short share-token fingerprint are
recorded, never a password or a usable token.
"""

from __future__ import annotations

import logging
from typing import Literal

from starlette.requests import Request

from app.core.security.share.share_hmac import token_fingerprint
from app.middleware.auth_audit import AuthEventType, log_auth_event
from app.platform_utils.deployment_capabilities import get_deployment_capabilities

logger = logging.getLogger(__name__)

LockoutScope = Literal["share_password", "webui_login"]

# Enough hex digits to tell shares apart in an audit view without exposing the full token hash.
_SUBJECT_LENGTH = 12


def report_lockout(scope: LockoutScope, *, client: str, subject: str | None = None) -> None:
    """Record that *client* was just locked out of *scope* (*subject* names the guarded share, when there is one)."""
    logger.warning("Lockout engaged: scope=%s client=%s subject=%s", scope, client, subject or "-")
    if not get_deployment_capabilities().enables_auth_audit:
        return
    metadata: dict[str, object] = {"scope": scope}
    if subject is not None:
        metadata["subject"] = subject
    log_auth_event(AuthEventType.RATE_LIMIT_EXCEEDED, client, metadata=metadata)


def report_share_lockout(request: Request, token: str) -> None:
    """Record that the requesting client was just locked out of the share behind *token*."""
    client = request.client.host if request.client else "unknown"
    report_lockout("share_password", client=client, subject=token_fingerprint(token)[:_SUBJECT_LENGTH])
