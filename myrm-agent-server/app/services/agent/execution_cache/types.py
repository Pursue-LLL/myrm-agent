"""Execution cache types — pooled BuiltExecutionUnit and execution mode.

[INPUT]
- myrm_agent_harness.api::SkillAgent (POS: harness agent 实例)

[OUTPUT]
- ExecutionMode, BuiltExecutionUnit

[POS]
execution_cache 类型层。定义 pooled/ephemeral 模式与可复用构建单元。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.api import SkillAgent


class ExecutionMode(StrEnum):
    """Whether a run may reuse a chat-scoped built execution unit."""

    POOLED = "pooled"
    EPHEMERAL = "ephemeral"


@dataclass(slots=True)
class BuiltExecutionUnit:
    """Heavy build artifacts kept warm across messages in one chat scope."""

    skill_agent: SkillAgent
    browser_session: object | None = None
    desktop_session: object | None = None
    checkpoint_helper: object | None = None
    current_thread_id: str | None = None

    async def teardown(self) -> None:
        """Fully close resources when evicting or deleting a chat scope."""
        if self.browser_session is not None:
            try:
                close = getattr(self.browser_session, "close", None)
                if callable(close):
                    result = close()
                    if hasattr(result, "__await__"):
                        await result
            except Exception:
                pass
            finally:
                self.browser_session = None

        if self.desktop_session is not None:
            try:
                close = getattr(self.desktop_session, "close", None)
                if callable(close):
                    result = close()
                    if hasattr(result, "__await__"):
                        await result
            except Exception:
                pass
            finally:
                self.desktop_session = None

        try:
            await self.skill_agent.close()
        except Exception:
            pass

        self.checkpoint_helper = None
        self.current_thread_id = None
