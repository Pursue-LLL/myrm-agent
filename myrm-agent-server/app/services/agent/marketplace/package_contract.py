"""Marketplace package contract and integrity gate.

[INPUT]
- pydantic::BaseModel / validators (POS: runtime schema validation engine)
- standard json/hashlib/hmac (POS: payload canonicalization + digest verification)

[OUTPUT]
- MarketplacePackageContract: strict import/export package schema
- build_marketplace_package(): normalized package builder with trust digest
- validate_marketplace_package(): fail-closed contract + integrity verification

[POS]
Marketplace package contract layer. Provides a single source of truth for
package type/version/trust semantics and enforces structural + integrity checks
before any import-side mutation happens.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MARKETPLACE_PACKAGE_TYPE = "myrm.marketplace.agent_profile"
MARKETPLACE_PACKAGE_SCHEMA_VERSION = 1
MARKETPLACE_TRUST_MODEL = "sha256-payload-v1"
MARKETPLACE_TRANSPORT_SIGNER = "control-plane"
MARKETPLACE_TRANSPORT_ALGORITHM = "hmac-sha256-v1"

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def _strip_and_require(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be a non-empty string")
    return stripped


def _strip_or_none(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _strip_and_require(value, field_name)


def _normalize_non_empty_string_list(values: list[str], field_name: str) -> list[str]:
    normalized: list[str] = []
    for idx, value in enumerate(values):
        if not isinstance(value, str):
            raise ValueError(f"{field_name}[{idx}] must be a string")
        normalized.append(_strip_and_require(value, f"{field_name}[{idx}]"))
    return normalized


def _validate_resource_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    if not normalized:
        raise ValueError("resources key must be a non-empty relative path")
    if normalized.startswith("/"):
        raise ValueError(f"resources path '{path}' must be relative")
    segments = [segment for segment in normalized.split("/") if segment]
    if not segments:
        raise ValueError(f"resources path '{path}' is invalid")
    if any(segment in {".", ".."} for segment in segments):
        raise ValueError(f"resources path '{path}' cannot contain '.' or '..'")
    return "/".join(segments)


class MarketplacePackageTrust(BaseModel):
    """Trust metadata attached to a package."""

    model_config = ConfigDict(extra="forbid")

    model: Literal[MARKETPLACE_TRUST_MODEL]
    payload_sha256: str
    transport_signer: Literal[MARKETPLACE_TRANSPORT_SIGNER] | None = None
    transport_algorithm: Literal[MARKETPLACE_TRANSPORT_ALGORITHM] | None = None
    transport_signature: str | None = None

    @field_validator("payload_sha256")
    @classmethod
    def validate_payload_sha256(cls, value: str) -> str:
        if not _SHA256_HEX_RE.match(value):
            raise ValueError("trust.payload_sha256 must be a lowercase sha256 hex string")
        return value

    @field_validator("transport_signature")
    @classmethod
    def validate_transport_signature(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _SHA256_HEX_RE.match(value):
            raise ValueError("trust.transport_signature must be a lowercase sha256 hex string")
        return value

    @model_validator(mode="after")
    def validate_transport_triplet(self) -> "MarketplacePackageTrust":
        any_present = any(
            value is not None
            for value in (
                self.transport_signer,
                self.transport_algorithm,
                self.transport_signature,
            )
        )
        all_present = all(
            value is not None
            for value in (
                self.transport_signer,
                self.transport_algorithm,
                self.transport_signature,
            )
        )
        if any_present and not all_present:
            raise ValueError(
                "trust.transport_signer/transport_algorithm/transport_signature must be provided together"
            )
        return self


class MarketplaceMcpConfigContract(BaseModel):
    """Bundled MCP configuration reference."""

    model_config = ConfigDict(extra="forbid")

    original_id: str
    tool_selections: list[str] | None = None

    @field_validator("original_id")
    @classmethod
    def validate_original_id(cls, value: str) -> str:
        return _strip_and_require(value, "bundled_mcp_configs.original_id")

    @field_validator("tool_selections")
    @classmethod
    def validate_tool_selections(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_non_empty_string_list(value, "bundled_mcp_configs.tool_selections")


class MarketplaceAgentProfileContract(BaseModel):
    """Agent profile payload for import/export."""

    model_config = ConfigDict(extra="allow")

    display_name: str
    description: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    model_selection: dict[str, object] | None = None
    skill_ids: list[str] = Field(default_factory=list)
    skill_configs: dict[str, dict[str, object]] | None = None
    subagent_ids: list[str] = Field(default_factory=list)
    mcp_ids: list[str] = Field(default_factory=list)
    mcp_tool_selections: dict[str, list[str]] | None = None
    enabled_builtin_tools: list[str] | None = None
    security_overrides: dict[str, object] | None = None
    prompt_mode: Literal["full", "lean", "naked", "search"] | None = None
    agent_type: Literal["individual", "team"] | None = None
    allow_discovery: bool | None = None
    personality_style: str = "professional"
    max_iterations: int | None = None
    workspace_policy: Literal["INHERIT_REQUESTER", "ISOLATED_COPY", "READ_ONLY_SANDBOX"] | None = None
    memory_policy: dict[str, object] | None = None
    engine_params: dict[str, object] | None = None
    auto_restore_domains: list[str] | None = None
    suggestion_prompts: list[str] | None = None
    openapi_services: list[dict[str, object]] | None = None
    command_bindings: list[dict[str, object]] | None = None
    notify_targets: list[dict[str, str]] | None = None
    home_directory: str | None = None
    browser_source: str | None = None
    dialog_policy: str | None = None
    session_recording: str | None = None
    cron_post_run_verify: bool | None = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return _strip_and_require(value, "agent_profile.display_name")

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _strip_and_require(value, "agent_profile.model")

    @field_validator("skill_ids")
    @classmethod
    def validate_skill_ids(cls, value: list[str]) -> list[str]:
        return _normalize_non_empty_string_list(value, "agent_profile.skill_ids")

    @field_validator("subagent_ids")
    @classmethod
    def validate_subagent_ids(cls, value: list[str]) -> list[str]:
        return _normalize_non_empty_string_list(value, "agent_profile.subagent_ids")

    @field_validator("mcp_ids")
    @classmethod
    def validate_mcp_ids(cls, value: list[str]) -> list[str]:
        return _normalize_non_empty_string_list(value, "agent_profile.mcp_ids")

    @field_validator("mcp_tool_selections")
    @classmethod
    def validate_mcp_tool_selections(
        cls, value: dict[str, list[str]] | None
    ) -> dict[str, list[str]] | None:
        if value is None:
            return None
        normalized: dict[str, list[str]] = {}
        for server_name, tools in value.items():
            normalized_key = _strip_and_require(server_name, "agent_profile.mcp_tool_selections key")
            normalized[normalized_key] = _normalize_non_empty_string_list(
                tools, f"agent_profile.mcp_tool_selections['{normalized_key}']"
            )
        return normalized

    @field_validator("enabled_builtin_tools")
    @classmethod
    def validate_enabled_builtin_tools(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_non_empty_string_list(value, "agent_profile.enabled_builtin_tools")

    @field_validator("auto_restore_domains")
    @classmethod
    def validate_auto_restore_domains(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_non_empty_string_list(value, "agent_profile.auto_restore_domains")

    @field_validator("suggestion_prompts")
    @classmethod
    def validate_suggestion_prompts(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_non_empty_string_list(value, "agent_profile.suggestion_prompts")

    @field_validator("home_directory")
    @classmethod
    def validate_home_directory(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _strip_and_require(value, "agent_profile.home_directory")

    @field_validator("browser_source")
    @classmethod
    def validate_browser_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _strip_and_require(value, "agent_profile.browser_source")

    @field_validator("dialog_policy")
    @classmethod
    def validate_dialog_policy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _strip_and_require(value, "agent_profile.dialog_policy")

    @field_validator("session_recording")
    @classmethod
    def validate_session_recording(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _strip_and_require(value, "agent_profile.session_recording")


class MarketplaceBundledSkillContract(BaseModel):
    """Skill bundle unit in marketplace package."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    content: str
    description: str = ""
    resources: dict[str, str] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _strip_and_require(value, "bundled_skills.id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _strip_and_require(value, "bundled_skills.name")

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return _strip_and_require(value, "bundled_skills.content")

    @field_validator("resources")
    @classmethod
    def validate_resources(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_path, content in value.items():
            if not isinstance(content, str):
                raise ValueError(f"resources['{raw_path}'] content must be a string")
            normalized_path = _validate_resource_path(raw_path)
            if normalized_path in normalized:
                raise ValueError(
                    f"resources contains duplicate normalized path '{normalized_path}'"
                )
            normalized[normalized_path] = content
        return normalized


class MarketplaceBundledSubagentContract(BaseModel):
    """Subagent bundle unit in marketplace package."""

    model_config = ConfigDict(extra="forbid")

    original_id: str
    profile: MarketplaceAgentProfileContract

    @field_validator("original_id")
    @classmethod
    def validate_original_id(cls, value: str) -> str:
        return _strip_and_require(value, "bundled_subagents.original_id")


class MarketplacePackageContract(BaseModel):
    """Complete marketplace package contract."""

    model_config = ConfigDict(extra="forbid")

    package_type: Literal[MARKETPLACE_PACKAGE_TYPE]
    schema_version: Literal[MARKETPLACE_PACKAGE_SCHEMA_VERSION]
    trust: MarketplacePackageTrust
    agent_profile: MarketplaceAgentProfileContract
    bundled_skills: list[MarketplaceBundledSkillContract] = Field(default_factory=list)
    bundled_mcp_configs: list[MarketplaceMcpConfigContract] = Field(default_factory=list)
    bundled_subagents: list[MarketplaceBundledSubagentContract] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_uniqueness(self) -> "MarketplacePackageContract":
        self._validate_unique(
            [skill.id for skill in self.bundled_skills], "bundled_skills.id"
        )
        self._validate_unique(
            [skill.name for skill in self.bundled_skills], "bundled_skills.name"
        )
        self._validate_unique(
            [sub.original_id for sub in self.bundled_subagents], "bundled_subagents.original_id"
        )
        self._validate_unique(
            [mcp.original_id for mcp in self.bundled_mcp_configs], "bundled_mcp_configs.original_id"
        )
        return self

    @staticmethod
    def _validate_unique(values: list[str], field_name: str) -> None:
        seen: set[str] = set()
        duplicated: set[str] = set()
        for value in values:
            if value in seen:
                duplicated.add(value)
            else:
                seen.add(value)
        if duplicated:
            duplicates = ", ".join(sorted(duplicated))
            raise ValueError(f"{field_name} contains duplicates: {duplicates}")


def _canonical_json(data: Mapping[str, object]) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_marketplace_payload_sha256(payload: Mapping[str, object]) -> str:
    """Compute canonical SHA-256 digest for package payload."""
    canonical = _canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_marketplace_transport_signature(
    *,
    payload_sha256: str,
    transport_secret: str,
    signer: str = MARKETPLACE_TRANSPORT_SIGNER,
    algorithm: str = MARKETPLACE_TRANSPORT_ALGORITHM,
) -> str:
    """Compute transport-level signature over payload digest."""
    normalized_secret = _strip_and_require(
        transport_secret, "transport_secret"
    )
    signing_message = f"{signer}:{algorithm}:{payload_sha256}"
    return hmac.new(
        normalized_secret.encode("utf-8"),
        signing_message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _payload_for_integrity(contract: MarketplacePackageContract) -> dict[str, object]:
    """Serialize payload exactly as integrity hashing input."""
    return contract.model_dump(exclude={"trust"})


def build_marketplace_package(
    *,
    agent_profile: dict[str, object],
    bundled_skills: list[dict[str, object]],
    bundled_mcp_configs: list[dict[str, object]],
    bundled_subagents: list[dict[str, object]],
) -> dict[str, object]:
    """Build a contract-compliant marketplace package with trust metadata."""
    provisional_package: dict[str, object] = {
        "package_type": MARKETPLACE_PACKAGE_TYPE,
        "schema_version": MARKETPLACE_PACKAGE_SCHEMA_VERSION,
        "agent_profile": agent_profile,
        "bundled_skills": bundled_skills,
        "bundled_mcp_configs": bundled_mcp_configs,
        "bundled_subagents": bundled_subagents,
        "trust": {
            "model": MARKETPLACE_TRUST_MODEL,
            "payload_sha256": "0" * 64,
        },
    }
    provisional_validated = MarketplacePackageContract.model_validate(provisional_package)
    normalized_payload = _payload_for_integrity(provisional_validated)
    package: dict[str, object] = dict(normalized_payload)
    package["trust"] = {
        "model": MARKETPLACE_TRUST_MODEL,
        "payload_sha256": compute_marketplace_payload_sha256(normalized_payload),
    }
    validated = MarketplacePackageContract.model_validate(package)
    return validated.model_dump()


def apply_marketplace_transport_signature(
    package: Mapping[str, object],
    *,
    transport_secret: str,
    signer: str = MARKETPLACE_TRANSPORT_SIGNER,
    algorithm: str = MARKETPLACE_TRANSPORT_ALGORITHM,
) -> dict[str, object]:
    """Attach transport-level signature to a validated package."""
    normalized_signer = _strip_or_none(signer, "trust.transport_signer")
    normalized_algorithm = _strip_or_none(
        algorithm, "trust.transport_algorithm"
    )
    if normalized_signer is None or normalized_algorithm is None:
        raise ValueError("transport signer and algorithm are required")

    validated = MarketplacePackageContract.model_validate(dict(package))
    signed = validated.model_dump()
    trust = dict(signed["trust"])
    trust["transport_signer"] = normalized_signer
    trust["transport_algorithm"] = normalized_algorithm
    trust["transport_signature"] = compute_marketplace_transport_signature(
        payload_sha256=validated.trust.payload_sha256,
        transport_secret=transport_secret,
        signer=normalized_signer,
        algorithm=normalized_algorithm,
    )
    signed["trust"] = trust
    return MarketplacePackageContract.model_validate(signed).model_dump()


def validate_marketplace_package(
    package: Mapping[str, object],
    *,
    require_transport_signature: bool = False,
    transport_secret: str | None = None,
) -> MarketplacePackageContract:
    """Validate package contract and integrity (fail-closed)."""
    validated = MarketplacePackageContract.model_validate(dict(package))
    payload = _payload_for_integrity(validated)
    expected_sha = compute_marketplace_payload_sha256(payload)
    if not hmac.compare_digest(expected_sha, validated.trust.payload_sha256):
        raise ValueError("Marketplace package integrity check failed (payload digest mismatch)")

    has_transport_signature = (
        validated.trust.transport_signer is not None
        or validated.trust.transport_algorithm is not None
        or validated.trust.transport_signature is not None
    )
    if require_transport_signature and not has_transport_signature:
        raise ValueError(
            "Marketplace package transport trust check failed (missing transport signature)"
        )

    if has_transport_signature:
        if transport_secret is None or not transport_secret.strip():
            raise ValueError(
                "Marketplace package transport trust check failed (transport secret is not configured)"
            )
        if validated.trust.transport_signer != MARKETPLACE_TRANSPORT_SIGNER:
            raise ValueError(
                "Marketplace package transport trust check failed (unexpected transport signer)"
            )
        if validated.trust.transport_algorithm != MARKETPLACE_TRANSPORT_ALGORITHM:
            raise ValueError(
                "Marketplace package transport trust check failed (unexpected transport algorithm)"
            )
        if validated.trust.transport_signature is None:
            raise ValueError(
                "Marketplace package transport trust check failed (missing transport signature digest)"
            )
        expected_transport_signature = compute_marketplace_transport_signature(
            payload_sha256=validated.trust.payload_sha256,
            transport_secret=transport_secret,
            signer=validated.trust.transport_signer,
            algorithm=validated.trust.transport_algorithm,
        )
        if not hmac.compare_digest(
            expected_transport_signature,
            validated.trust.transport_signature,
        ):
            raise ValueError(
                "Marketplace package transport trust check failed (signature mismatch)"
            )

    return validated


__all__ = [
    "MARKETPLACE_TRANSPORT_ALGORITHM",
    "MARKETPLACE_TRANSPORT_SIGNER",
    "MARKETPLACE_PACKAGE_SCHEMA_VERSION",
    "MARKETPLACE_PACKAGE_TYPE",
    "MARKETPLACE_TRUST_MODEL",
    "MarketplacePackageContract",
    "apply_marketplace_transport_signature",
    "build_marketplace_package",
    "compute_marketplace_payload_sha256",
    "compute_marketplace_transport_signature",
    "validate_marketplace_package",
]
