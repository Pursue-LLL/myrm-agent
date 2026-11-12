"""Context loading for agent prompt injection.

[INPUT]
- memory.protocols.relational::RelationalStoreProtocol (POS: relational persistence)
- memory.types::{ProfileEntry, ProceduralMemory} (POS: memory data models)

[OUTPUT]
- load_context: Loads profile, rules (one list: locked first, then newest first), and working state for agent prompt
- WORKING_STATE_PROFILE_KEY, WORKING_STATE_UPDATED_AT_KEY, WORKING_STATE_TTL_DAYS: Constants
- CHAT_SCOPED_PROFILE_KEYS: the profile entries that hold one chat's own words and leave with it

[POS]
Context loading for agent system prompt injection. Fetches user profile entries,
active rules, and working state from relational storage.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory.tool_guidance import ToolGuidanceItem
from myrm_agent_harness.toolkits.memory.types import (
    ProceduralMemory,
    ProfileEntry,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.protocols.relational import RelationalStoreProtocol

logger = logging.getLogger(__name__)

WORKING_STATE_PROFILE_KEY = "__working_state"
WORKING_STATE_UPDATED_AT_KEY = "__working_state_updated_at"
WORKING_STATE_TTL_DAYS = 7

# The working state is the digest of one chat, injected into later chats until it expires, so it records the chat it was
# written from and goes when that chat is deleted. Every other profile entry is a fact the user keeps.
CHAT_SCOPED_PROFILE_KEYS = frozenset({WORKING_STATE_PROFILE_KEY, WORKING_STATE_UPDATED_AT_KEY})


async def load_context(
    relational: RelationalStoreProtocol,
    *,
    include_profile: bool = True,
    include_rules: bool = True,
    namespaces: list[str] | None = None,
) -> dict[str, object]:
    ctx: dict[str, object] = {"global_profile": {}, "peer_profile": {}, "rules": []}

    tasks: dict[str, asyncio.Task[object]] = {}
    if include_profile:
        tasks["profile"] = asyncio.create_task(relational.list_profiles(namespaces=namespaces))
    if include_rules:
        tasks["rules"] = asyncio.create_task(relational.list_rules(active_only=True, namespaces=namespaces))

    results = dict(
        zip(
            tasks.keys(),
            await asyncio.gather(*tasks.values(), return_exceptions=True),
            strict=True,
        )
    )

    if "profile" in results and not isinstance(results["profile"], Exception):
        entries = results["profile"]
        if isinstance(entries, list):
            global_profile = {}
            peer_profile = {}
            working_state: str | None = None
            working_state_updated_at: str | None = None
            for e in entries:
                if not isinstance(e, ProfileEntry):
                    continue
                if e.key == WORKING_STATE_PROFILE_KEY:
                    working_state = str(e.value)
                    continue
                if e.key == WORKING_STATE_UPDATED_AT_KEY:
                    working_state_updated_at = str(e.value)
                    continue
                if e.scope.primary_namespace == "global":
                    global_profile[e.key] = e.value
                else:
                    peer_profile[e.key] = e.value
            ctx["global_profile"] = global_profile
            ctx["peer_profile"] = peer_profile

            if working_state and working_state_updated_at:
                try:
                    updated_at = datetime.fromisoformat(working_state_updated_at)
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=UTC)
                    if (datetime.now(UTC) - updated_at).days < WORKING_STATE_TTL_DAYS:
                        ctx["working_state"] = working_state
                except (ValueError, TypeError):
                    ctx["working_state"] = working_state
            elif working_state:
                ctx["working_state"] = working_state

    if "rules" in results and not isinstance(results["rules"], Exception):
        rules_raw = results["rules"]
        rule_entries: list[dict[str, str | bool]] = []
        guidance_items: list[ToolGuidanceItem] = []
        if isinstance(rules_raw, list):
            for r in rules_raw:
                if isinstance(r, ProceduralMemory):
                    if r.tool_name:
                        guidance_items.append(
                            ToolGuidanceItem(
                                id=r.id,
                                tool_name=r.tool_name,
                                rule_text=r.action,
                                trigger_pattern=r.trigger,
                                confidence=1.0 if r.is_user_locked else 0.8,
                                is_pinned=r.is_user_locked,
                                env_fingerprint=str(r.metadata.get("env_fingerprint"))
                                if r.metadata.get("env_fingerprint")
                                else None,
                                agent_id=str(r.metadata.get("agent_id")) if r.metadata.get("agent_id") else None,
                                source="manual" if r.is_user_locked else "self_healing",
                                hit_count=int(r.metadata.get("hit_count", 1)),
                            )
                        )

                    rule_entries.append(
                        {
                            "trigger": r.trigger,
                            "action": r.action,
                            "source": r.source.value,
                            "user_endorsed": r.is_user_locked,
                        }
                    )
        # Storage hands the rules out newest first; the stable sort puts the locked ones ahead of them.
        rule_entries.sort(key=lambda rule: not rule["user_endorsed"])
        ctx["rules"] = rule_entries
        ctx["raw_tool_guidance_items"] = guidance_items

    return ctx
