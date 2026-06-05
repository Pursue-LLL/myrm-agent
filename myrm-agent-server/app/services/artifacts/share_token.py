"""Signed tokens for read-only public artifact preview links.

[INPUT]
- app.config.settings::settings (POS: signing key material)

[OUTPUT]
- create_artifact_share_token / parse_artifact_share_token
- is_shareable_artifact: unified share eligibility (name, type, extension inference)

[POS]
Stateless HMAC tokens for time-limited public artifact viewing (no DB row).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from myrm_agent_harness.agent.artifacts.constants import (
    ArtifactType,
    infer_artifact_type_from_extension,
)

from app.config.settings import settings

_TOKEN_VERSION = 1
_DEFAULT_TTL_SECONDS = 7 * 24 * 3600
_SHAREABLE_ARTIFACT_TYPES: frozenset[str] = frozenset(
    {ArtifactType.HTML.value, ArtifactType.PDF.value, ArtifactType.DOCUMENT.value}
)


@dataclass(frozen=True)
class ArtifactShareClaims:
    artifact_id: str
    version_id: str
    exp: int
    artifact_type: str | None = None


def _signing_secret() -> bytes:
    for candidate in (
        settings.config_encryption_key.get_secret_value(),
        settings.internal_service_key.get_secret_value(),
        settings.sandbox_api_key.get_secret_value(),
    ):
        if candidate and candidate.strip():
            return candidate.strip().encode("utf-8")
    # Local dev fallback: stable per data dir (single-tenant only).
    seed = (settings.database.state_dir or "myrm-local").encode("utf-8")
    return hashlib.sha256(b"artifact-share:" + seed).digest()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def create_artifact_share_token(
    artifact_id: str,
    version_id: str,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    artifact_type: str | None = None,
) -> tuple[str, int]:
    """Return (token, expires_at_unix)."""
    exp = int(time.time()) + max(60, ttl_seconds)
    payload: dict[str, Any] = {
        "v": _TOKEN_VERSION,
        "aid": artifact_id,
        "vid": version_id,
        "exp": exp,
    }
    if artifact_type and artifact_type.strip():
        payload["typ"] = artifact_type.strip().lower()
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_signing_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}", exp


def parse_artifact_share_token(token: str) -> ArtifactShareClaims | None:
    """Verify signature and expiry; return None when invalid."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expected = hmac.new(_signing_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        raw: dict[str, Any] = json.loads(_b64url_decode(body))
    except (json.JSONDecodeError, ValueError):
        return None
    if raw.get("v") != _TOKEN_VERSION:
        return None
    artifact_id = raw.get("aid")
    version_id = raw.get("vid")
    exp = raw.get("exp")
    if not isinstance(artifact_id, str) or not isinstance(version_id, str) or not isinstance(exp, int):
        return None
    if exp < int(time.time()):
        return None
    artifact_type_raw = raw.get("typ")
    artifact_type = artifact_type_raw if isinstance(artifact_type_raw, str) else None
    return ArtifactShareClaims(
        artifact_id=artifact_id,
        version_id=version_id,
        exp=exp,
        artifact_type=artifact_type,
    )


SHAREABLE_NAME_SUFFIXES: frozenset[str] = frozenset({".html", ".htm", ".pdf", ".md", ".markdown", ".txt"})


def is_shareable_artifact_name(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(suffix) for suffix in SHAREABLE_NAME_SUFFIXES)


def is_shareable_artifact(name: str, artifact_type: str | None = None) -> bool:
    """Match frontend share gates: suffix, client type, or harness extension inference."""
    if is_shareable_artifact_name(name):
        return True
    normalized = (artifact_type or "").strip().lower()
    if normalized in _SHAREABLE_ARTIFACT_TYPES:
        return True
    inferred = infer_artifact_type_from_extension(name)
    return inferred.value in _SHAREABLE_ARTIFACT_TYPES
