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

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def _strip_and_require(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be a non-empty string")
    return stripped


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

    @field_validator("payload_sha256")
    @classmethod
    def validate_payload_sha256(cls, value: str) -> str:
        if not _SHA256_HEX_RE.match(value):
            raise ValueError("trust.payload_sha256 must be a lowercase sha256 hex string")
        return value


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
    skill_ids: list[str] = Field(default_factory=list)
    subagent_ids: list[str] = Field(default_factory=list)
    mcp_ids: list[str] = Field(default_factory=list)
    mcp_tool_selections: dict[str, list[str]] | None = None
    enabled_builtin_tools: list[str] | None = None
    personality_style: str = "professional"
    max_iterations: int | None = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return _strip_and_require(value, "agent_profile.display_name")

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


def validate_marketplace_package(package: Mapping[str, object]) -> MarketplacePackageContract:
    """Validate package contract and integrity (fail-closed)."""
    validated = MarketplacePackageContract.model_validate(dict(package))
    payload = _payload_for_integrity(validated)
    expected_sha = compute_marketplace_payload_sha256(payload)
    if not hmac.compare_digest(expected_sha, validated.trust.payload_sha256):
        raise ValueError("Marketplace package integrity check failed (payload digest mismatch)")
    return validated


__all__ = [
    "MARKETPLACE_PACKAGE_SCHEMA_VERSION",
    "MARKETPLACE_PACKAGE_TYPE",
    "MARKETPLACE_TRUST_MODEL",
    "MarketplacePackageContract",
    "build_marketplace_package",
    "compute_marketplace_payload_sha256",
    "validate_marketplace_package",
]
