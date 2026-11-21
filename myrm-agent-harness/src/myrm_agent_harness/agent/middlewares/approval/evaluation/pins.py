"""The files a model response's file calls were judged on, and the check that a call still opens them.

The calls of one model message are judged together before the first of them runs. A call early in the message can then
change what a path later in it leads to (a link to a credential file made under a name that did not exist when the
later call was judged), so the later call would open a file nobody looked at. Each file call is therefore pinned to the
files it opens when it is judged, and the tool-call hook that runs it asks whether it still opens only those.

[INPUT]
- agent.security.judged_paths::judged_file_paths (POS: every file a file tool may open: the typed ones and the respelling of a read)
- agent.security.path_rules::PATH_CHECKED_PERMISSIONS (POS: the zone verdict and the canonical places of a call's files)
- agent.security.tool_registry::resolve_permission_type (POS: Tool metadata registry: permission mapping, canonical params, safety metadata)
- core.security.path::opened_path (POS: Aggregation facade for the path security domain)
- core.security.tool_registry::host_file_paths (POS: the host files a call names, in every form a reader could open them)
- .record::PATH_PINS_KEY, PathPin (POS: The stored verdicts and the pins of file calls)

[OUTPUT]
- build_path_pins: the pin of each file call among a model response's calls, by call id
- pin_of: the pin the graph state holds for one call
- path_moved: whether a call now opens a file its pin does not hold

[POS]
The judge-time half and the run-time half of the path pin, kept together so both read a call's files the same way.
The pin is the permission engine's own target set (``judged_file_paths``) resolved through ``opened_path``, so it
names exactly the files the verdict was about.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeGuard

from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.security.judged_paths import judged_file_paths
from myrm_agent_harness.agent.security.path_rules import PATH_CHECKED_PERMISSIONS
from myrm_agent_harness.agent.security.tool_registry import resolve_permission_type
from myrm_agent_harness.core.security.path import opened_path
from myrm_agent_harness.core.security.tool_registry import host_file_paths

from .record import PATH_PINS_KEY, PathPin


def _opened(permission: str, args: dict[str, object], workspace_root: str | None) -> list[str]:
    """The files a call opens, every link followed, sorted; ``""`` stands for a text no file can be named by."""
    return sorted(
        {opened_path(path, workspace_root) or "" for path in judged_file_paths(permission, args, workspace_root)}
    )


def build_path_pins(calls: Sequence[ToolCall], workspace_root: str | None) -> dict[str, PathPin]:
    """The pin of every file call among *calls*, keyed by call id; any other call opens no judged file."""
    pins: dict[str, PathPin] = {}
    for call in calls:
        call_id, args = call.get("id"), call["args"]
        permission = resolve_permission_type(call["name"], args)
        if call_id and permission in PATH_CHECKED_PERMISSIONS:
            pins[call_id] = PathPin(typed=host_file_paths(args), opened=_opened(permission, args, workspace_root))
    return pins


def _is_pin(value: object) -> TypeGuard[PathPin]:
    return isinstance(value, dict) and isinstance(value.get("typed"), list) and isinstance(value.get("opened"), list)


def pin_of(state: Mapping[str, object], call_id: str) -> PathPin | None:
    """The pin kept in the graph state for the call *call_id*, or None when it has none."""
    pins = state.get(PATH_PINS_KEY)
    pin = pins.get(call_id) if isinstance(pins, dict) else None
    return pin if _is_pin(pin) else None


def path_moved(pin: PathPin, tool_name: str, args: dict[str, object], workspace_root: str | None) -> bool:
    """Whether the call now opens a file its pin does not hold: a link or a rename has since changed what a path leads to.

    A subset is enough: a file created in the meantime opens the place its name always pointed at. A call whose typed
    paths differ from the pinned ones was edited by the person, who approved the text they wrote; it is not held to
    the files the original text opened.
    """
    if host_file_paths(args) != pin["typed"]:
        return False
    return not set(_opened(resolve_permission_type(tool_name, args), args, workspace_root)) <= set(pin["opened"])
