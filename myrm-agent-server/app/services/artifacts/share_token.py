"""Signed tokens for read-only public artifact preview links.

[INPUT]
- app.core.security.share_hmac (POS: shared HMAC signing primitives)

[OUTPUT]
- create_artifact_share_token / parse_artifact_share_token
- rebuild_artifact_share_token: reconstruct unprotected tokens from persisted
  registry fields (deterministic HMAC → same payload + expiry yields the same
  token), so GUI list endpoints can expose the share path without storing it
- is_shareable_artifact: unified share eligibility (name, type, extension inference)

[POS]
Stateless HMAC tokens for time-limited public artifact viewing (no DB row).
Delegates signing to the shared share_hmac module; adds artifact-specific
payload fields and shareable-type checks.
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.agent.artifacts.constants import (
    ArtifactType,
    infer_artifact_type_from_extension,
)

from app.core.security.share_hmac import (
    create_share_token,
    parse_share_token,
    sign_share_token,
)

_SALT = "artifact-share"
_DEFAULT_TTL_SECONDS = 7 * 24 * 3600
_MAX_TTL_SECONDS = 30 * 24 * 3600
_SHAREABLE_ARTIFACT_TYPES: frozenset[str] = frozenset(
    {ArtifactType.HTML.value, ArtifactType.PDF.value, ArtifactType.DOCUMENT.value}
)


@dataclass(frozen=True)
class ArtifactShareClaims:
    artifact_id: str
    version_id: str
    exp: int
    artifact_type: str | None = None
    password_protected: bool = False


def create_artifact_share_token(
    artifact_id: str,
    version_id: str,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    artifact_type: str | None = None,
    password: str | None = None,
) -> tuple[str, int]:
    """Return (token, expires_at_unix)."""
    payload: dict[str, object] = {"aid": artifact_id, "vid": version_id}
    if artifact_type and artifact_type.strip():
        payload["typ"] = artifact_type.strip().lower()
    return create_share_token(
        payload,
        salt=_SALT,
        ttl_seconds=max(60, ttl_seconds),
        max_ttl_seconds=_MAX_TTL_SECONDS,
        password=password,
    )


def rebuild_artifact_share_token(
    artifact_id: str,
    version_id: str,
    *,
    expires_at_unix: int,
    artifact_type: str | None,
) -> str:
    """Reconstruct an unprotected share token from persisted registry fields.

    Tokens are deterministic (same payload + expiry → same token), so the link
    can be rebuilt without storing the raw token. Password-protected shares
    cannot be rebuilt here: the password is never persisted.
    """
    payload: dict[str, object] = {"aid": artifact_id, "vid": version_id}
    if artifact_type and artifact_type.strip():
        payload["typ"] = artifact_type.strip().lower()
    return sign_share_token(payload, salt=_SALT, exp=expires_at_unix)


def parse_artifact_share_token(
    token: str,
    *,
    password: str | None = None,
) -> ArtifactShareClaims | None:
    """Verify signature and expiry; return None when invalid."""
    raw = parse_share_token(token, salt=_SALT, password=password)
    if raw is None:
        return None
    artifact_id = raw.get("aid")
    version_id = raw.get("vid")
    exp = raw.get("exp")
    if not isinstance(artifact_id, str) or not isinstance(version_id, str) or not isinstance(exp, int):
        return None
    artifact_type_raw = raw.get("typ")
    artifact_type = artifact_type_raw if isinstance(artifact_type_raw, str) else None
    return ArtifactShareClaims(
        artifact_id=artifact_id,
        version_id=version_id,
        exp=exp,
        artifact_type=artifact_type,
        password_protected=raw.get("p") == 1,
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
