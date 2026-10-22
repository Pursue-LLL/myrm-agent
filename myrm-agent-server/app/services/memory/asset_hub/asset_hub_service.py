"""Agent Memory Asset Hub Service for 4-tier cognitive asset catalog & game-like equipment slots.

[INPUT] asset_hub_types.py
[OUTPUT] MemoryAssetHubService: asset storage, ACL filtering, and agent equipment binding.
[POS] app/services/memory/asset_hub/asset_hub_service.py
"""

from datetime import datetime, timezone
import uuid
from app.services.memory.asset_hub.asset_hub_types import (
    AclScope,
    AclUpdateRequest,
    AgentEquipmentSummary,
    CreateAssetRequest,
    EquipmentSlot,
    MemoryAsset,
    MemoryAssetType,
)

STANDARD_SLOT_DEFS: list[tuple[str, str, list[MemoryAssetType]]] = [
    ("slot_chat", "Chat Memory Slot", [MemoryAssetType.CHAT_MEMORY]),
    ("slot_skill", "Skill Artifact Slot", [MemoryAssetType.SKILL]),
    ("slot_wiki", "Wiki Knowledge Slot", [MemoryAssetType.WIKI]),
    ("slot_code", "Code Graph Slot", [MemoryAssetType.CODE_GRAPH]),
]


class MemoryAssetHubService:
    """Manages cognitive assets catalog, granular ACL policies, and agent equipment slots."""

    def __init__(self) -> None:
        self._assets: dict[str, MemoryAsset] = {}
        # agent_id -> {slot_id -> asset_id}
        self._equipment: dict[str, dict[str, str]] = {}
        self._seed_default_assets()

    def _seed_default_assets(self) -> None:
        """Seed rich foundational assets across the four cognitive dimensions."""
        default_items: list[MemoryAsset] = [
            MemoryAsset(
                id="asset-chat-dev-prefs",
                name="Developer Preferences & Code Style",
                description="Long-term user preferences for concise typing, PEP8, and modern React hooks.",
                asset_type=MemoryAssetType.CHAT_MEMORY,
                acl_scope=AclScope.TEAM,
                owner_agent_id="system",
                project_id="default-project",
                content_preview="User prefers strict typing, zero-any policy, and fast async iteration.",
                tags=["preferences", "code-style", "general"],
                size_bytes=2048,
            ),
            MemoryAsset(
                id="asset-skill-fastapi-guru",
                name="FastAPI & Async Architect Skill",
                description="Specialized skill routines for high-throughput ASGI endpoints and DI management.",
                asset_type=MemoryAssetType.SKILL,
                acl_scope=AclScope.TEAM,
                owner_agent_id="system",
                project_id="default-project",
                content_preview="def build_async_router(): ... includes robust error wrappers and DI.",
                tags=["skill", "backend", "fastapi"],
                size_bytes=4096,
            ),
            MemoryAsset(
                id="asset-wiki-open-arch",
                name="System Topology & Sandboxing Wiki",
                description="Comprehensive knowledge graph documenting agent isolation and Volume mounts.",
                asset_type=MemoryAssetType.WIKI,
                acl_scope=AclScope.PROJECT,
                owner_agent_id="agent-arch",
                project_id="default-project",
                content_preview="Root architecture separates harness execution engine from business servers.",
                tags=["wiki", "architecture", "sandbox"],
                size_bytes=8192,
            ),
            MemoryAsset(
                id="asset-code-harness-ast",
                name="Myrm Harness AST & Dependency Graph",
                description="Extracted symbol graph covering tools, agent loops, and middleware hooks.",
                asset_type=MemoryAssetType.CODE_GRAPH,
                acl_scope=AclScope.PROJECT,
                owner_agent_id="system",
                project_id="default-project",
                content_preview="digraph G { AgentRunner -> ToolRegistry; ContextEngine -> VectorDB; }",
                tags=["codegraph", "ast", "dependencies"],
                size_bytes=16384,
            ),
            MemoryAsset(
                id="asset-chat-secret-sandbox",
                name="Private Security Sandbox Notes",
                description="Confidential audit findings restricted solely to the dedicated Security Auditor agent.",
                asset_type=MemoryAssetType.CHAT_MEMORY,
                acl_scope=AclScope.PRIVATE,
                owner_agent_id="agent-security-auditor",
                project_id="default-project",
                allowed_agent_ids=["agent-security-auditor"],
                content_preview="E2EE salt rotation vectors and enclave isolated execution keys.",
                tags=["security", "confidential"],
                size_bytes=3072,
            ),
        ]
        for item in default_items:
            self._assets[item.id] = item

    def check_access(
        self,
        asset: MemoryAsset,
        requesting_agent_id: str | None,
        project_id: str | None = None,
    ) -> bool:
        """Evaluate if an agent has permission to inspect or equip an asset."""
        if requesting_agent_id is None:
            return True

        # Check project constraint first for project-scoped assets
        if asset.acl_scope == AclScope.PROJECT and project_id:
            if asset.project_id != project_id:
                return False

        if asset.acl_scope == AclScope.TEAM:
            return True

        if asset.acl_scope == AclScope.PRIVATE:
            return asset.owner_agent_id == requesting_agent_id or requesting_agent_id in asset.allowed_agent_ids

        return True

    def list_assets(
        self,
        requesting_agent_id: str | None = None,
        asset_type: MemoryAssetType | None = None,
        acl_scope: AclScope | None = None,
        project_id: str | None = None,
    ) -> list[MemoryAsset]:
        """List assets matching criteria with strict ACL security filtering."""
        results: list[MemoryAsset] = []
        for asset in self._assets.values():
            if asset_type and asset.asset_type != asset_type:
                continue
            if acl_scope and asset.acl_scope != acl_scope:
                continue
            if not self.check_access(asset, requesting_agent_id, project_id):
                continue
            results.append(asset)
        return results

    def get_asset(self, asset_id: str) -> MemoryAsset | None:
        """Retrieve an asset by ID."""
        return self._assets.get(asset_id)

    def create_asset(
        self,
        req: CreateAssetRequest,
        owner_agent_id: str = "system",
        project_id: str = "default-project",
    ) -> MemoryAsset:
        """Create and register a new cognitive asset."""
        now_str = datetime.now(timezone.utc).isoformat()
        asset_id = f"asset-{req.asset_type.value[:4]}-{uuid.uuid4().hex[:8]}"
        new_asset = MemoryAsset(
            id=asset_id,
            name=req.name,
            description=req.description,
            asset_type=req.asset_type,
            acl_scope=req.acl_scope,
            owner_agent_id=owner_agent_id,
            project_id=project_id,
            allowed_agent_ids=req.allowed_agent_ids or ([owner_agent_id] if req.acl_scope == AclScope.PRIVATE else []),
            content_preview=req.content_preview,
            tags=req.tags,
            size_bytes=len(req.content_preview.encode("utf-8")) or 1024,
            created_at=now_str,
            updated_at=now_str,
        )
        self._assets[new_asset.id] = new_asset
        return new_asset

    def update_asset_acl(
        self,
        asset_id: str,
        req: AclUpdateRequest,
        requesting_agent_id: str | None = None,
    ) -> MemoryAsset | None:
        """Update the ACL scope and allowed agents for a cognitive asset."""
        asset = self._assets.get(asset_id)
        if not asset:
            return None

        if requesting_agent_id and asset.owner_agent_id not in (requesting_agent_id, "system"):
            raise PermissionError(f"Agent '{requesting_agent_id}' is not the owner of asset '{asset_id}'")

        asset.acl_scope = req.acl_scope
        asset.allowed_agent_ids = req.allowed_agent_ids
        asset.updated_at = datetime.now(timezone.utc).isoformat()
        return asset

    def get_agent_equipment(self, agent_id: str) -> AgentEquipmentSummary:
        """Return the complete 4-slot equipment summary for an agent."""
        equipped_map = self._equipment.get(agent_id, {})
        slots: list[EquipmentSlot] = []
        total_equipped = 0

        for slot_id, slot_name, allowed_types in STANDARD_SLOT_DEFS:
            eq_asset_id = equipped_map.get(slot_id)
            eq_asset = self._assets.get(eq_asset_id) if eq_asset_id else None
            if eq_asset:
                total_equipped += 1

            slots.append(
                EquipmentSlot(
                    slot_id=slot_id,
                    slot_name=slot_name,
                    allowed_types=allowed_types,
                    equipped_asset_id=eq_asset_id,
                    equipped_asset=eq_asset,
                )
            )

        return AgentEquipmentSummary(
            agent_id=agent_id,
            slots=slots,
            total_equipped=total_equipped,
            max_slots=len(STANDARD_SLOT_DEFS),
        )

    def equip_asset(
        self,
        agent_id: str,
        slot_id: str,
        asset_id: str,
        project_id: str | None = None,
    ) -> AgentEquipmentSummary:
        """Equip an asset into a slot with ACL validation and slot-type conformity."""
        asset = self._assets.get(asset_id)
        if not asset:
            raise ValueError(f"Asset '{asset_id}' does not exist")

        if not self.check_access(asset, agent_id, project_id):
            raise PermissionError(f"Agent '{agent_id}' is not authorized to equip private/restricted asset '{asset_id}'")

        target_slot_def = next((s for s in STANDARD_SLOT_DEFS if s[0] == slot_id), None)
        if not target_slot_def:
            raise ValueError(f"Invalid equipment slot ID '{slot_id}'")

        allowed_types = target_slot_def[2]
        if asset.asset_type not in allowed_types:
            raise ValueError(
                f"Asset type '{asset.asset_type.value}' is not allowed in slot '{slot_id}' "
                f"(expected: {[t.value for t in allowed_types]})"
            )

        if agent_id not in self._equipment:
            self._equipment[agent_id] = {}

        self._equipment[agent_id][slot_id] = asset_id
        return self.get_agent_equipment(agent_id)

    def unequip_asset(self, agent_id: str, slot_id: str) -> AgentEquipmentSummary:
        """Unequip an asset from a given slot."""
        if agent_id in self._equipment and slot_id in self._equipment[agent_id]:
            del self._equipment[agent_id][slot_id]

        return self.get_agent_equipment(agent_id)


# Singleton instance
memory_asset_hub_service = MemoryAssetHubService()
