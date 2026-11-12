"""memory_store MCP tool: persist knowledge / event / preference / rule / instruction memories.

[INPUT]
- toolkits.memory.agent_surface.mcp_server.common::{ManagerResolver, parse_string_list} (POS: Stateless helpers for the recall/list/store/manage tool handlers)
- toolkits.memory.agent_surface.mcp_server.request_context::get_request_wiki_boundary_enabled (POS: ContextVar bindings for per-request scoping)
- toolkits.memory.manager::MemoryManager (POS: memory lifecycle manager; routes writes through the approval queue when approval_required)
- toolkits.memory._internal.scope::MemoryWriteTarget (POS: bound / shared write target)
- toolkits.memory.types::RuleSource (POS: rule provenance enum)
- toolkits.memory.agent_surface.memory_recall_formatting::{format_preference_save_ack, format_write_ack} (POS: recall sanitize and save-ack SSOT)
- toolkits.memory.agent_surface.wiki_memory_boundary (POS: wiki-memory write boundary heuristics)
- toolkits.memory.agent_surface.write_failure_feedback (POS: LLM-readable write failure messages)
- toolkits.memory._internal.unit_interval::require_unit_interval (POS: 0.0-1.0 score range check shared with update)
- toolkits.memory.agent_surface._memory_agent_tool_descriptions::MEMORY_SAVE_IMPORTANCE_FIELD_DESCRIPTION (POS: argument-level scope note for importance)

[OUTPUT]
- register_store_tool: register memory_store on an MCPServer

[POS]
Write plane (create) of the MCP adapter; external agents write straight to the manager (no session buffer).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from myrm_agent_harness.toolkits.memory._internal.scope import MemoryWriteTarget
from myrm_agent_harness.toolkits.memory._internal.unit_interval import require_unit_interval
from myrm_agent_harness.toolkits.memory.agent_surface._memory_agent_tool_descriptions import (
    MEMORY_SAVE_IMPORTANCE_FIELD_DESCRIPTION,
)
from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server.common import ManagerResolver, parse_string_list
from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server.request_context import (
    get_request_wiki_boundary_enabled,
)
from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_formatting import (
    format_preference_save_ack,
    format_write_ack,
)
from myrm_agent_harness.toolkits.memory.agent_surface.wiki_memory_boundary import (
    looks_like_wiki_document,
    record_wiki_memory_save_rejection,
    wiki_memory_save_rejection_message,
)
from myrm_agent_harness.toolkits.memory.agent_surface.write_failure_feedback import write_failure_feedback
from myrm_agent_harness.toolkits.memory.types import MemoryType, RuleSource

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

_VALID_CATEGORIES = ("knowledge", "event", "preference", "rule", "instruction")


def _parse_write_target(value: str) -> MemoryWriteTarget | None:
    if value == "bound":
        return "bound"
    if value == "shared":
        return "shared"
    return None


async def _store_knowledge(
    mgr: MemoryManager,
    content: str,
    *,
    importance: float,
    tags: list[str],
    write_target: MemoryWriteTarget,
) -> str:
    # Type-enabled, not dense-capable: without an embedding backend the type
    # lives in the BM25 sparse mirror and stays writable.
    if MemoryType.SEMANTIC not in mgr.get_enabled_types():
        return "Knowledge memory is not enabled."
    # Only knowledge stores the score; any other category ignores it and must never fail on it.
    require_unit_interval("importance", importance, action="saved")
    mem = await mgr.add_knowledge(
        content, importance=importance, tags=tags, write_target=write_target, honor_approval=True
    )
    return format_write_ack("Knowledge", mem)


async def _store_event(mgr: MemoryManager, content: str, *, write_target: MemoryWriteTarget) -> str:
    if MemoryType.EPISODIC not in mgr.get_enabled_types():
        return "Event memory is not enabled."
    mem = await mgr.add_event(content, event_type="agent_observation", write_target=write_target, honor_approval=True)
    return format_write_ack("Event", mem)


async def _store_preference(mgr: MemoryManager, content: str, *, preference_key: str | None) -> str:
    if not mgr.has_relational:
        return "Profile memory is not enabled."
    if not preference_key:
        return "Preference requires 'preference_key'."
    result = await mgr.set_profile_attribute(preference_key, content)
    if result is not None:
        return f"Preference '{preference_key}' submitted for approval"
    return format_preference_save_ack(preference_key, content)


async def _store_rule(
    mgr: MemoryManager,
    content: str,
    *,
    trigger: str | None,
    keywords: list[str],
) -> str:
    if not mgr.has_relational:
        return "Procedural memory is not enabled."
    if not trigger:
        return "Rule requires 'rule_trigger'."
    mem = await mgr.add_rule(trigger, content, trigger_keywords=keywords, honor_approval=True)
    return format_write_ack("Rule", mem)


async def _store_instruction(mgr: MemoryManager, content: str) -> str:
    if not mgr.has_relational:
        return "Procedural memory is not enabled."
    mem = await mgr.add_rule("always", content, source=RuleSource.AGENT_SELF, honor_approval=True)
    return format_write_ack("Instruction", mem)


def register_store_tool(mcp: MCPServer, resolve: ManagerResolver, *, description: str) -> None:
    """Register memory_store on ``mcp``; ``resolve`` supplies the request's MemoryManager."""

    @mcp.tool(name="memory_store", description=description)
    async def memory_store(
        content: str,
        category: str = "knowledge",
        importance: Annotated[float, Field(description=MEMORY_SAVE_IMPORTANCE_FIELD_DESCRIPTION)] = 0.5,
        tags: str | list[str] | None = None,
        write_target: str = "bound",
        preference_key: str | None = None,
        rule_trigger: str | None = None,
        rule_keywords: str | list[str] | None = None,
    ) -> str:
        """Store a memory.

        Args:
            content: The memory content to store.
            category: knowledge | event | preference | rule | instruction.
            importance: 0.0-1.0 importance score (default 0.5); knowledge only, other categories ignore it.
            tags: Tags (knowledge only). Accepts a comma-separated
                string, a JSON array, or a raw list.
            write_target: "bound" (agent scope) or "shared" (broadest namespace).
            preference_key: Required for preference category (e.g. "language", "framework").
            rule_trigger: Required for rule category — describes when the rule applies.
            rule_keywords: Trigger keywords for rules. Accepts a comma-separated
                string, a JSON array, or a raw list.
        """
        if not content or not content.strip():
            return "Error: content cannot be empty."

        if category not in _VALID_CATEGORIES:
            return f"Error: invalid category '{category}'. Valid: {', '.join(_VALID_CATEGORIES)}"
        target = _parse_write_target(write_target)
        if target is None:
            return "Error: write_target must be 'bound' or 'shared'."

        mgr = resolve()
        parsed_tags = parse_string_list(tags)
        parsed_keywords = parse_string_list(rule_keywords)

        if (
            get_request_wiki_boundary_enabled()
            and category in ("knowledge", "event")
            and looks_like_wiki_document(content)
        ):
            record_wiki_memory_save_rejection()
            return wiki_memory_save_rejection_message(include_tool_hint=False)

        try:
            if category == "knowledge":
                return await _store_knowledge(
                    mgr, content, importance=importance, tags=parsed_tags, write_target=target
                )
            if category == "event":
                return await _store_event(mgr, content, write_target=target)
            if category == "preference":
                return await _store_preference(mgr, content, preference_key=preference_key)
            if category == "rule":
                return await _store_rule(mgr, content, trigger=rule_trigger, keywords=parsed_keywords)
            if category == "instruction":
                return await _store_instruction(mgr, content)
            return f"Unknown category: {category}"
        except Exception as e:
            return write_failure_feedback("MCP memory_store", e, fallback="Failed to store memory")
