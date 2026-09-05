"""Agent filesystem bundle serialization, export, and workspace sync service.

[INPUT]
- app.database.dto::AgentCreate, ModelSelection, CommandBindingConfig
- app.services.agent.agent_service::AgentService
- myrm_agent_harness.backends.profiles.types::AgentProfile
- pathlib::Path

[OUTPUT]
- AgentBundleCodec: Serialize/deserialize between AgentProfile / AgentCreate and filesystem directory tree:
    .myrm/agents/{agent_id}/
      ├── AGENTS.md (Natural language persona & system prompt)
      ├── agent.manifest.yaml (Declarative configuration & model routing)
      └── mcp.json (MCP tool configs & whitelist selections)
- AgentBundleService: High-level import/export and workspace synchronization

[POS]
Agent-as-Code filesystem bundle layer for Myrm Agent. Bridges DB runtime
profiles and filesystem GitOps/Workspace tree without breaking existing
database models or multi-tenant sandbox boundaries.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException

from app.database.dto import AgentCreate, AgentUpdate
from app.services.agent.agent_service import AgentService

logger = logging.getLogger(__name__)

BUNDLE_DIR_NAME = ".myrm/agents"
MANIFEST_FILENAME = "agent.manifest.yaml"
PROMPT_FILENAME = "AGENTS.md"
MCP_FILENAME = "mcp.json"


@dataclass(frozen=True, slots=True)
class AgentBundleData:
    """In-memory representation of an exported filesystem agent bundle."""

    agent_id: str
    name: str
    prompt: str
    manifest_yaml: str
    mcp_json: str


class AgentBundleCodec:
    """Encodes and decodes Agent definitions to/from standardized filesystem bundles."""

    @staticmethod
    def encode_bundle(
        agent_dict: dict[str, Any],
    ) -> dict[str, str]:
        """Convert an agent profile dict into filesystem bundle file contents.

        Returns a dict of relative paths to text contents:
        {
            "AGENTS.md": "...",
            "agent.manifest.yaml": "...",
            "mcp.json": "..."
        }
        """
        # 1. Extract system prompt for AGENTS.md
        system_prompt = (agent_dict.get("system_prompt") or "").strip()
        agents_md = system_prompt if system_prompt else f"# {agent_dict.get('name', 'Agent')}\n"

        # 2. Extract MCP configuration for mcp.json
        mcp_data = {
            "mcp_ids": agent_dict.get("mcp_ids") or [],
            "mcp_tool_selections": agent_dict.get("mcp_tool_selections") or {},
        }
        mcp_json = json.dumps(mcp_data, indent=2, ensure_ascii=False)

        # 3. Build manifest data excluding prompt and mcp details
        manifest_data: dict[str, Any] = {
            "schema_version": "1.0",
            "id": agent_dict.get("id"),
            "name": agent_dict.get("name"),
            "description": agent_dict.get("description"),
            "agent_type": agent_dict.get("agent_type", "individual"),
            "prompt_mode": agent_dict.get("prompt_mode", "full"),
            "personality_style": agent_dict.get("personality_style", "professional"),
            "model_selection": agent_dict.get("model_selection"),
            "skill_ids": agent_dict.get("skill_ids") or [],
            "subagent_ids": agent_dict.get("subagent_ids") or [],
            "enabled_builtin_tools": agent_dict.get("enabled_builtin_tools"),
            "max_iterations": agent_dict.get("max_iterations"),
            "workspace_policy": agent_dict.get("workspace_policy", "INHERIT_REQUESTER"),
        }
        manifest_yaml = yaml.safe_dump(manifest_data, sort_keys=False, allow_unicode=True)

        return {
            PROMPT_FILENAME: agents_md,
            MANIFEST_FILENAME: manifest_yaml,
            MCP_FILENAME: mcp_json,
        }

    @staticmethod
    def decode_bundle(
        files: dict[str, str],
    ) -> dict[str, Any]:
        """Parse bundle files into an AgentCreate-compatible dictionary."""
        manifest_raw = files.get(MANIFEST_FILENAME, "")
        manifest = yaml.safe_load(manifest_raw) if manifest_raw else {}
        if not isinstance(manifest, dict):
            manifest = {}

        # Parse AGENTS.md
        prompt = files.get(PROMPT_FILENAME, "").strip()

        # Parse mcp.json
        mcp_raw = files.get(MCP_FILENAME, "")
        mcp_data = json.loads(mcp_raw) if mcp_raw else {}
        if not isinstance(mcp_data, dict):
            mcp_data = {}

        merged: dict[str, Any] = {
            "name": manifest.get("name") or "Imported Agent",
            "description": manifest.get("description"),
            "system_prompt": prompt,
            "agent_type": manifest.get("agent_type", "individual"),
            "prompt_mode": manifest.get("prompt_mode", "full"),
            "personality_style": manifest.get("personality_style", "professional"),
            "model_selection": manifest.get("model_selection"),
            "skill_ids": manifest.get("skill_ids") or [],
            "subagent_ids": manifest.get("subagent_ids") or [],
            "enabled_builtin_tools": manifest.get("enabled_builtin_tools"),
            "max_iterations": manifest.get("max_iterations"),
            "workspace_policy": manifest.get("workspace_policy", "INHERIT_REQUESTER"),
            "mcp_ids": mcp_data.get("mcp_ids") or [],
            "mcp_tool_selections": mcp_data.get("mcp_tool_selections") or {},
        }
        return merged


class AgentBundleService:
    """Handles workspace disk synchronization and filesystem exports."""

    @classmethod
    def _validate_safe_bundle_path(cls, agent_id: str, workspace_dir: str | Path) -> Path:
        """Validate agent_id and compute safe target bundle directory."""
        if not agent_id or "/" in agent_id or "\\" in agent_id or ".." in agent_id:
            raise HTTPException(status_code=400, detail=f"Invalid agent ID or path traversal detected: {agent_id}")
        workspace_root = Path(workspace_dir).resolve()
        base_dir = (workspace_root / BUNDLE_DIR_NAME).resolve()
        target_dir = (base_dir / agent_id).resolve()
        try:
            target_dir.relative_to(base_dir)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=f"Path traversal detected in agent_id: {agent_id}") from err
        return target_dir

    @classmethod
    async def export_bundle(cls, agent_id: str) -> AgentBundleData:
        """Export agent as in-memory filesystem bundle representation."""
        agent = await AgentService.get_agent_by_id(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

        from app.api.agents._agent_response import _to_agent_response
        agent_resp = _to_agent_response(agent, show_system_prompt=True)
        agent_dict = agent_resp.model_dump()
        bundle_files = AgentBundleCodec.encode_bundle(agent_dict)

        return AgentBundleData(
            agent_id=agent_id,
            name=agent_dict.get("name") or agent_id,
            prompt=bundle_files.get(PROMPT_FILENAME, ""),
            manifest_yaml=bundle_files.get(MANIFEST_FILENAME, ""),
            mcp_json=bundle_files.get(MCP_FILENAME, ""),
        )

    @classmethod
    async def write_bundle_to_workspace(
        cls,
        agent_id: str,
        workspace_dir: str | Path,
    ) -> Path:
        """Write serialized agent bundle into workspace directory tree."""
        target_dir = cls._validate_safe_bundle_path(agent_id, workspace_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        bundle = await cls.export_bundle(agent_id)
        (target_dir / PROMPT_FILENAME).write_text(bundle.prompt, encoding="utf-8")
        (target_dir / MANIFEST_FILENAME).write_text(bundle.manifest_yaml, encoding="utf-8")
        (target_dir / MCP_FILENAME).write_text(bundle.mcp_json, encoding="utf-8")

        logger.info("Successfully exported agent %s to workspace bundle at %s", agent_id, target_dir)
        return target_dir

    @classmethod
    def read_bundle_from_workspace(
        cls,
        agent_id: str,
        workspace_dir: str | Path,
    ) -> AgentCreate:
        """Read and parse bundle directory from workspace into AgentCreate DTO."""
        target_dir = cls._validate_safe_bundle_path(agent_id, workspace_dir)
        if not target_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"Bundle directory does not exist: {target_dir}")

        files: dict[str, str] = {}
        for expected in (PROMPT_FILENAME, MANIFEST_FILENAME, MCP_FILENAME):
            p = target_dir / expected
            if p.is_file():
                files[expected] = p.read_text(encoding="utf-8")

        agent_dict = AgentBundleCodec.decode_bundle(files)
        return AgentCreate.model_validate(agent_dict)

    @classmethod
    async def sync_workspace_to_agent(
        cls,
        agent_id: str,
        workspace_dir: str | Path,
    ) -> dict[str, Any]:
        """Update existing agent in DB from workspace bundle."""
        agent_dto = cls.read_bundle_from_workspace(agent_id, workspace_dir)
        agent_update = AgentUpdate(
            name=agent_dto.name,
            description=agent_dto.description,
            system_prompt=agent_dto.system_prompt,
            agent_type=agent_dto.agent_type,
            prompt_mode=agent_dto.prompt_mode,
            personality_style=agent_dto.personality_style,
            model_selection=agent_dto.model_selection,
            skill_ids=agent_dto.skill_ids,
            subagent_ids=agent_dto.subagent_ids,
            enabled_builtin_tools=agent_dto.enabled_builtin_tools,
            max_iterations=agent_dto.max_iterations,
            workspace_policy=agent_dto.workspace_policy,
            mcp_ids=agent_dto.mcp_ids,
            mcp_tool_selections=agent_dto.mcp_tool_selections,
        )
        outcome = await AgentService.update_agent(agent_id, agent_update)
        return {
            "agent_id": agent_id,
            "snapshot_saved": outcome.snapshot_saved if hasattr(outcome, "snapshot_saved") else True,
            "synced": True,
        }

    @classmethod
    async def export_agent_to_workspace(
        cls,
        agent_id: str,
        workspace_root: Path,
    ) -> Path:
        """Export an agent profile into the specified workspace directory tree (alias)."""
        return await cls.write_bundle_to_workspace(agent_id, workspace_root)

    @classmethod
    async def import_agent_from_bundle_dir(
        cls,
        bundle_dir: Path,
    ) -> str:
        """Import or update an agent from a bundle directory."""
        if not bundle_dir.is_dir():
            raise ValueError(f"Bundle directory does not exist: {bundle_dir}")

        files: dict[str, str] = {}
        for expected in (PROMPT_FILENAME, MANIFEST_FILENAME, MCP_FILENAME):
            p = bundle_dir / expected
            if p.is_file():
                files[expected] = p.read_text(encoding="utf-8")

        agent_dict = AgentBundleCodec.decode_bundle(files)
        agent_create = AgentCreate.model_validate(agent_dict)
        agent_create.is_built_in = False

        agent = await AgentService.create_agent(agent_create)
        return agent.id
