"""Agent filesystem bundle service (Dual-Track SSOT).

[INPUT]
- agent_id: str, workspace_dir: str | Path
- AgentService, _to_agent_response, AgentCreate, AgentUpdate

[OUTPUT]
- AgentBundle: in-memory bundle representation (prompt, manifest_yaml, mcp_json)
- write_bundle_to_workspace: writes .myrm/agents/{agent_id}/ bundle to filesystem
- read_bundle_from_workspace: parses filesystem bundle into validated AgentCreate
- sync_agent_to_workspace / sync_workspace_to_agent: bidirectional synchronization

[POS]
Provides filesystem-based Agent-as-Code capabilities (.myrm/agents/{id}/).
Separates natural language prompt into AGENTS.md, structured configuration into
agent.manifest.yaml, and tool configuration into mcp.json for Git-friendly management.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.api.agents._agent_response import _to_agent_response
from app.core.utils.errors import not_found_error, validation_error
from app.database.dto import AgentCreate, AgentUpdate
from app.services.agent.agent_service import AgentService

logger = logging.getLogger(__name__)

_SENSITIVE_AUTH_KEYS = frozenset(
    {"api_key", "bearer_token", "client_secret", "password", "username", "auth_token"}
)


@dataclass(frozen=True)
class AgentBundle:
    agent_id: str
    name: str
    prompt: str
    manifest_yaml: str
    mcp_json: str


def _strip_sensitive_in_place(data: dict[str, object]) -> None:
    """Strip secret credentials from configuration payload in-place."""
    for key in list(data.keys()):
        if key.lower() in _SENSITIVE_AUTH_KEYS:
            data.pop(key, None)

    openapi_services = data.get("openapi_services")
    if isinstance(openapi_services, list):
        for svc in openapi_services:
            if isinstance(svc, dict):
                auth = svc.get("auth")
                if isinstance(auth, dict):
                    for k in list(auth.keys()):
                        if k.lower() in _SENSITIVE_AUTH_KEYS:
                            auth.pop(k, None)

    gateway = data.get("tool_gateway_config")
    if isinstance(gateway, dict):
        for k in list(gateway.keys()):
            if k.lower() in _SENSITIVE_AUTH_KEYS:
                gateway.pop(k, None)


def _resolve_bundle_dir(workspace_dir: str | Path, agent_id: str) -> Path:
    """Resolve and validate the bundle directory inside a workspace."""
    clean_agent_id = agent_id.strip()
    if not clean_agent_id or ".." in clean_agent_id or "/" in clean_agent_id or "\\" in clean_agent_id:
        raise validation_error(f"Invalid agent ID format: {agent_id}")

    ws_path = Path(workspace_dir).resolve()
    target_dir = (ws_path / ".myrm" / "agents" / clean_agent_id).resolve()

    try:
        target_dir.relative_to(ws_path)
    except ValueError as e:
        raise validation_error("Agent bundle path escapes workspace root") from e

    return target_dir


class AgentBundleService:
    """Service for exporting, importing, and synchronizing Agent filesystem bundles."""

    @staticmethod
    async def export_bundle(agent_id: str) -> AgentBundle:
        """Export an agent profile into an in-memory AgentBundle struct."""
        agent = await AgentService.get_agent_by_id(agent_id)
        if not agent:
            raise not_found_error("Agent")

        agent_resp = _to_agent_response(agent, show_system_prompt=True)
        raw_dict = agent_resp.model_dump(exclude={"id", "user_id", "created_at", "updated_at"})
        _strip_sensitive_in_place(raw_dict)

        prompt = str(raw_dict.pop("system_prompt", "") or "")

        mcp_ids = raw_dict.pop("mcp_ids", []) or []
        mcp_tool_selections = raw_dict.pop("mcp_tool_selections", None)
        mcp_payload: dict[str, object] = {
            "mcp_ids": mcp_ids,
            "mcp_tool_selections": mcp_tool_selections or {},
        }
        mcp_json = json.dumps(mcp_payload, indent=2, ensure_ascii=False)

        manifest_yaml = yaml.safe_dump(
            raw_dict,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )

        return AgentBundle(
            agent_id=agent_id,
            name=agent.name,
            prompt=prompt,
            manifest_yaml=manifest_yaml,
            mcp_json=mcp_json,
        )

    @classmethod
    async def write_bundle_to_workspace(
        cls,
        agent_id: str,
        workspace_dir: str | Path,
    ) -> Path:
        """Serialize an agent bundle and write files to .myrm/agents/{agent_id}/."""
        bundle = await cls.export_bundle(agent_id)
        target_dir = _resolve_bundle_dir(workspace_dir, agent_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        (target_dir / "AGENTS.md").write_text(bundle.prompt, encoding="utf-8")
        (target_dir / "agent.manifest.yaml").write_text(bundle.manifest_yaml, encoding="utf-8")
        (target_dir / "mcp.json").write_text(bundle.mcp_json, encoding="utf-8")

        logger.info("Agent bundle written to workspace: %s", target_dir)
        return target_dir

    @staticmethod
    def read_bundle_from_workspace(
        agent_id: str,
        workspace_dir: str | Path,
    ) -> AgentCreate:
        """Parse .myrm/agents/{agent_id}/ filesystem bundle into AgentCreate DTO."""
        target_dir = _resolve_bundle_dir(workspace_dir, agent_id)
        manifest_path = target_dir / "agent.manifest.yaml"
        if not manifest_path.exists():
            raise not_found_error(f"agent.manifest.yaml in {target_dir}")

        try:
            raw_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(raw_manifest, dict):
                raise validation_error("agent.manifest.yaml must contain a YAML mapping")
        except yaml.YAMLError as e:
            raise validation_error(f"Failed to parse agent.manifest.yaml: {e}") from e

        prompt_path = target_dir / "AGENTS.md"
        if prompt_path.exists():
            raw_manifest["system_prompt"] = prompt_path.read_text(encoding="utf-8")

        mcp_path = target_dir / "mcp.json"
        if mcp_path.exists():
            try:
                mcp_data = json.loads(mcp_path.read_text(encoding="utf-8"))
                if isinstance(mcp_data, dict):
                    if "mcp_ids" in mcp_data and isinstance(mcp_data["mcp_ids"], list):
                        raw_manifest["mcp_ids"] = mcp_data["mcp_ids"]
                    if "mcp_tool_selections" in mcp_data and isinstance(mcp_data["mcp_tool_selections"], dict):
                        raw_manifest["mcp_tool_selections"] = mcp_data["mcp_tool_selections"]
            except json.JSONDecodeError as e:
                raise validation_error(f"Failed to parse mcp.json: {e}") from e

        try:
            return AgentCreate.model_validate(raw_manifest)
        except ValidationError as e:
            raise validation_error(f"Validation error in agent bundle: {e}") from e

    @classmethod
    async def sync_workspace_to_agent(
        cls,
        agent_id: str,
        workspace_dir: str | Path,
    ) -> dict[str, object]:
        """Apply filesystem bundle changes from .myrm/agents/{agent_id}/ into DB profile."""
        dto = cls.read_bundle_from_workspace(agent_id, workspace_dir)
        existing = await AgentService.get_agent_by_id(agent_id)
        if not existing:
            raise not_found_error("Agent")

        update_payload = AgentUpdate.model_validate(dto.model_dump(exclude_none=True))
        outcome = await AgentService.update_agent(agent_id, update_payload)
        return {
            "agent_id": agent_id,
            "name": outcome.profile.name,
            "snapshot_saved": outcome.snapshot_saved,
            "synced_from": str(_resolve_bundle_dir(workspace_dir, agent_id)),
        }
