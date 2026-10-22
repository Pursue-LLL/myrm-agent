"""[INPUT]
- myrm_agent_harness.agent.context_management.capability_matrix: CapabilityDiscoveryEngine, ContextStateSnapshot
- .registry: SYSTEM_COMMAND_MATRIX

[OUTPUT]
- CommandMatrixService: Business service managing capability matrix queries and heuristic suggestions

[POS]
Server-side business service for Item 38 P0. Strictly under 200 lines. Zero `Any`.
"""

from __future__ import annotations

import logging
import threading
from typing import ClassVar, Literal

from myrm_agent_harness.agent.context_management.capability_matrix import (
    CapabilityDiscoveryEngine,
    CommandMatrixEntry,
    ContextStateSnapshot,
)

from .registry import SYSTEM_COMMAND_MATRIX

logger = logging.getLogger(__name__)


class CommandMatrixService:
    """Singleton service governing the system command matrix and heuristic recommendations."""

    _instance: ClassVar[CommandMatrixService | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._commands: list[CommandMatrixEntry] = list(SYSTEM_COMMAND_MATRIX)

    @classmethod
    def get_instance(cls) -> CommandMatrixService:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def get_command_catalog(
        self,
        category: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, object]]:
        """Returns catalog entries optionally filtered by domain category or fuzzy search query."""
        results: list[CommandMatrixEntry] = self._commands

        if category and category.strip():
            cat = category.strip()
            results = [e for e in results if e.category == cat]

        if query and query.strip():
            q = query.strip().lower()
            results = [
                e
                for e in results
                if (
                    q in e.command.lower()
                    or q in e.title_zh.lower()
                    or q in e.title_en.lower()
                    or q in e.description_zh.lower()
                    or q in e.description_en.lower()
                    or any(q in t.lower() for t in e.tags)
                )
            ]

        return [self._serialize_entry(e) for e in results]

    def suggest_commands(
        self,
        session_id: str,
        status: Literal["idle", "running", "paused", "interrupted", "error"] = "idle",
        running_step_count: int = 0,
        recent_tools: list[str] | None = None,
        mastered_commands: list[str] | None = None,
        max_results: int = 3,
    ) -> list[dict[str, object]]:
        """Heuristically recommends contextual capability chips using the Harness engine."""
        snapshot = ContextStateSnapshot(
            session_id=session_id,
            status=status,
            running_step_count=running_step_count,
            recent_tools=recent_tools or [],
            user_prompt_focused=True,
            mastered_commands=mastered_commands or [],
        )

        chips = CapabilityDiscoveryEngine.evaluate_recommendations(
            context=snapshot,
            max_results=max_results,
        )

        return [
            {
                "chip_id": c.chip_id,
                "command": c.command,
                "label_zh": c.label_zh,
                "label_en": c.label_en,
                "reason_zh": c.reason_zh,
                "reason_en": c.reason_en,
                "priority": c.priority,
                "insert_prompt": c.insert_prompt,
            }
            for c in chips
        ]

    @classmethod
    def _serialize_entry(cls, entry: CommandMatrixEntry) -> dict[str, object]:
        return {
            "command": entry.command,
            "category": entry.category,
            "title_zh": entry.title_zh,
            "title_en": entry.title_en,
            "description_zh": entry.description_zh,
            "description_en": entry.description_en,
            "shortcut": entry.shortcut,
            "prompt_template": entry.prompt_template,
            "tags": entry.tags,
            "requires_running_task": entry.requires_running_task,
        }
