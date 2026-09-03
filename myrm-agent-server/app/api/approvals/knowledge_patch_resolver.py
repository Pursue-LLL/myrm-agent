"""Knowledge patch resolution logic for Wiki vault and Procedural memory.

[INPUT]
- app.database.models.approval::ApprovalRecord
- app.services.wiki.vault.resolver::resolve_wiki_vault_path
- myrm_agent_harness.toolkits.wiki::WikiStructure
- myrm_agent_harness.toolkits.wiki.pipeline.raw_gate::publish_raw, RawConflictPolicy, RawPublishRequest
- app.services.memory.runtime::get_shared_memory_manager

[OUTPUT]
- handle_knowledge_patch_resolution: Ingest approved knowledge patch to Wiki or Procedural memory

[POS]
Decoupled resolution handler for knowledge_patch approval records, keeping router.py within line budget.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.database.models.approval import ApprovalRecord

logger = logging.getLogger(__name__)


async def handle_knowledge_patch_resolution(record: ApprovalRecord, decision: str) -> None:
    """Ingest approved knowledge patch to Wiki vault or Procedural memory."""
    if decision != "approve":
        logger.info("Knowledge patch %s rejected by user", record.id)
        return

    payload = record.payload or {}
    target_type = str(payload.get("target_type", "wiki")).lower()
    title = str(payload.get("title", "")).strip() or "Untitled Knowledge Patch"
    content = str(payload.get("content", "")).strip()
    trigger_condition = str(payload.get("trigger_condition", "")).strip()
    rationale = str(payload.get("rationale", "")).strip()
    agent_id = record.agent_id or "default"

    if target_type == "wiki":
        try:
            from app.services.wiki.vault.resolver import resolve_wiki_vault_path
            from myrm_agent_harness.toolkits.wiki import WikiStructure
            from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import (
                RawConflictPolicy,
                RawPublishRequest,
                publish_raw,
            )

            vault_path = resolve_wiki_vault_path(agent_id)
            structure = WikiStructure(vault_path)
            structure.ensure_structure()

            safe_slug = re.sub(r"[^\w\-\u4e00-\u9fa5]+", "_", title).strip("_") or "patch"
            file_name = f"patch_{safe_slug}.md"
            doc_content = (
                f"# {title}\n\n"
                f"{content}\n\n"
                f"---\n"
                f"- **Trigger**: {trigger_condition}\n"
                f"- **Rationale**: {rationale}\n"
                f"- **Source**: Session Blind Spot Auto-Patch\n"
            )
            await publish_raw(
                structure,
                RawPublishRequest(
                    relative_path=file_name,
                    content=doc_content,
                    conflict_policy=RawConflictPolicy.RENAME,
                ),
                caller="guardian_blind_spot",
            )
            logger.info("Knowledge patch %s written to wiki vault: %s", record.id, file_name)
        except Exception as exc:
            logger.warning("Failed to publish knowledge patch %s to wiki: %s", record.id, exc)

    elif target_type == "procedural":
        try:
            from app.services.memory.runtime import get_shared_memory_manager
            from myrm_agent_harness.toolkits.memory.relational.models import (
                ProceduralMemory,
                RuleSource,
            )

            manager = await get_shared_memory_manager()
            rel = getattr(manager, "relational_store", None)
            if rel:
                await rel.add_procedural_rule(
                    ProceduralMemory(
                        content=content,
                        trigger=trigger_condition,
                        action=f"Apply rule: {title}",
                        reasoning=rationale,
                        source=RuleSource.USER,
                    )
                )
                logger.info("Knowledge patch %s added to procedural memory", record.id)
        except Exception as exc:
            logger.warning("Failed to write knowledge patch %s to procedural memory: %s", record.id, exc)

    elif target_type == "skill_gap":
        logger.info("Knowledge patch %s (skill gap: %s) acknowledged and recorded", record.id, title)
