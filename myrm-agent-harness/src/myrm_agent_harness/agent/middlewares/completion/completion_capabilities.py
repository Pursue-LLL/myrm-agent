"""What a run can do, as the completion guard needs to know it before holding the run to a demand.

The guard blocks a completion for a missing todo update, an unsaved deliverable or absent external evidence.
Each demand can be met only by a run that holds the tool for it: a delegated child without ``todo_write`` has no
list to finish, a run without ``file_write_tool`` (or under a policy that denies ``file_write``) cannot save a
file, a run without a web, browser or MCP tool cannot look anything up. A demand the run can never meet only
burns one paid model call per rejection.

Each probe is asked per call, not once: the registry is filled after the middleware chain is built, and the
policy of a turn arrives with the turn.

[INPUT]
- agent.middlewares._session_context::get_security_config, resolve_security_config_from_runtime (POS: the policy of the turn, else the one bound to the run)
- agent.middlewares.completion.completion_guard_external_evidence::can_produce_external_evidence (POS: which tools can produce external evidence)
- agent.security.engine::file_write_disabled (POS: whether the policy denies file_write)
- agent.tool_management::ToolRegistry (POS: the tools the run holds)

[OUTPUT]
- CompletionCapabilities: the three probes; the defaults hold a run to every demand
- capabilities_of(): probes that read a run's registry and policy

[POS]
Capability layer of the CompletionGuard: the guard decides whether to block, this module decides what the run is
able to do about it. Keeps tool-registry and policy reading out of the guard and out of the middleware builder.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.middlewares._session_context import (
    get_security_config,
    resolve_security_config_from_runtime,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard_external_evidence import (
    can_produce_external_evidence,
)
from myrm_agent_harness.agent.security.engine import file_write_disabled

if TYPE_CHECKING:
    from myrm_agent_harness.agent.tool_management import ToolRegistry


def _always() -> bool:
    return True


def _always_for(runtime: object) -> bool:
    return True


@dataclass(frozen=True, slots=True)
class CompletionCapabilities:
    """Whether the run can meet each demand the completion guard makes.

    keeps_todo_list:
        The run keeps a todo list, i.e. was given ``todo_write``. Only then does an unfinished todo block
        completion.
    can_save_files:
        The run can save a file, given the runtime of the call. Only then is a deliverable code block in the
        answer held to being saved (and staged into the workspace when the demand fails).
    can_gather_evidence:
        The run holds a tool that can produce external evidence. Only then is a freshness question held to
        having it; a run without one is asked once to say plainly that it could not check.
    """

    keeps_todo_list: Callable[[], bool] = _always
    can_save_files: Callable[[object], bool] = _always_for
    can_gather_evidence: Callable[[], bool] = _always


def capabilities_of(registry: ToolRegistry) -> CompletionCapabilities:
    """Probes that read what ``registry`` holds, and the policy of the call, each time they are asked."""

    def keeps_todo_list() -> bool:
        return registry.has_tool("todo_write")

    def can_save_files(runtime: object) -> bool:
        # The policy is read the way tool approval reads it (the turn's snapshot, else the one bound to the
        # run), so the demand is never one approval would refuse.
        if not registry.has_tool("file_write_tool"):
            return False
        return not file_write_disabled(resolve_security_config_from_runtime(runtime) or get_security_config())

    def can_gather_evidence() -> bool:
        return can_produce_external_evidence(registry.tool_names())

    return CompletionCapabilities(
        keeps_todo_list=keeps_todo_list,
        can_save_files=can_save_files,
        can_gather_evidence=can_gather_evidence,
    )
