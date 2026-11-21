"""A file call opens the files it was judged on, or it does not run.

The calls of one model message are judged together before the first of them runs, and the calls that conflict then run
one after another in the model's order. A call early in the message can change what a path later in it leads to (a link
to a credential file made under a name that did not exist when the later call was judged), so the later call would
open a file nobody looked at. These tests drive the shipped middleware stack, the way a run builds it, through such
messages, through approval pauses and through the cases that must keep working.
"""

from __future__ import annotations

import shlex
from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from myrm_agent_harness.agent.middlewares._session_context import set_security_config
from myrm_agent_harness.agent.middlewares.approval import set_approval_session
from myrm_agent_harness.agent.middlewares.approval.helpers import clear_all_session_denials_for_tests
from myrm_agent_harness.agent.security.engine import merge
from myrm_agent_harness.agent.security.types import (
    DEFAULT_RULESET,
    PermissionAction,
    PermissionRule,
    PrivacyPolicy,
    SecurityConfig,
)
from myrm_agent_harness.core.security.audit import get_audit_entries
from tests.support.shipped_graph import shipped_agent, shipped_session

# ``SECRET=`` would be masked in what a tool returns; a neutral marker shows whether the file was read.
DOTENV = "GREETING=hello-from-dotenv"

RAN: list[str] = []
WORKSPACE: list[Path] = []


@tool
def file_read_tool(paths: list[str]) -> str:
    """Read the files."""
    RAN.append("read")
    return "\n".join((WORKSPACE[0] / path).read_text() for path in paths)


@tool
def file_write_tool(path: str, content: str) -> str:
    """Write a file."""
    RAN.append("write")
    (WORKSPACE[0] / path).write_text(content)
    return "written"


@tool
def bash_code_execute_tool(command: str) -> str:
    """Run one of the commands that change the workspace's files."""
    RAN.append(command)
    match shlex.split(command):
        case ["ln", "-s", target, link]:
            (WORKSPACE[0] / link).symlink_to(target)
        case ["touch", name]:
            (WORKSPACE[0] / name).touch()
        case ["mv", source, target]:
            (WORKSPACE[0] / source).rename(WORKSPACE[0] / target)
    return "done"


TOOLS = [file_read_tool, file_write_tool, bash_code_execute_tool]


def _call(call_id: str, name: str, args: dict[str, object]) -> dict[str, object]:
    return {"id": call_id, "name": name, "args": args}


def _turn(*calls: dict[str, object]) -> AIMessage:
    return AIMessage(content="", tool_calls=list(calls))


LINK_THEN_READ = _turn(
    _call("c1", "bash_code_execute_tool", {"command": "ln -s .env notes.txt"}),
    _call("c2", "file_read_tool", {"paths": ["notes.txt"]}),
)
DONE = AIMessage(content="done")


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".env").write_text(DOTENV)
    RAN.clear()
    WORKSPACE[:] = [root]
    yield root
    WORKSPACE.clear()


@pytest.fixture(autouse=True)
def _approval_session() -> Iterator[None]:
    clear_all_session_denials_for_tests()
    set_approval_session("path-pin")
    yield
    set_approval_session("")
    clear_all_session_denials_for_tests()


def _asking_config(*rules: PermissionRule) -> SecurityConfig:
    """A run that asks a person about whatever its ruleset does not allow."""
    return SecurityConfig(
        yolo_mode_enabled=False,
        privacy_policy=PrivacyPolicy(enabled=False),
        ruleset=merge(DEFAULT_RULESET, rules),
    )


def _shell_allowed() -> tuple[PermissionRule, ...]:
    return (
        PermissionRule("shell_exec", "*", PermissionAction.ALLOW),
        PermissionRule("code_interpreter", "*", PermissionAction.ALLOW),
    )


def _answers(result: dict[str, object]) -> dict[str, ToolMessage]:
    messages = result["messages"]
    assert isinstance(messages, list)
    return {m.tool_call_id: m for m in messages if isinstance(m, ToolMessage)}


def _moved_calls() -> list[str | None]:
    return [entry.tool_call_id for entry in get_audit_entries() if entry.decision == "PATH_MOVED_REJECT"]


THREAD = {"configurable": {"thread_id": "t"}}


async def test_a_read_through_a_link_an_earlier_call_of_the_message_made_is_refused(workspace: Path) -> None:
    _, agent = shipped_agent([LINK_THEN_READ, DONE], TOOLS, registered=TOOLS)

    with shipped_session(workspace):
        answers = _answers(await agent.ainvoke({"messages": [HumanMessage(content="go")]}))

    assert RAN == ["ln -s .env notes.txt"]
    assert answers["c1"].status == "success"
    assert answers["c2"].status == "error"
    assert DOTENV not in str(answers["c2"].content)
    assert _moved_calls() == ["c2"]


async def test_a_write_through_a_link_an_earlier_call_made_into_a_denied_place_is_refused(workspace: Path) -> None:
    (workspace / "private").mkdir()
    first = _turn(
        _call("c1", "bash_code_execute_tool", {"command": "ln -s private shortcut"}),
        _call("c2", "file_write_tool", {"path": "shortcut/plan.md", "content": "planted"}),
    )
    _, agent = shipped_agent([first, DONE], TOOLS, registered=TOOLS)

    with shipped_session(workspace):
        set_security_config(
            _asking_config(*_shell_allowed(), PermissionRule("file_write", "private/*", PermissionAction.DENY))
        )
        answers = _answers(await agent.ainvoke({"messages": [HumanMessage(content="go")]}))

    assert not (workspace / "private" / "plan.md").exists()
    assert answers["c2"].status == "error"
    assert _moved_calls() == ["c2"]


async def test_the_refused_read_is_judged_afresh_when_the_model_asks_for_it_again(workspace: Path) -> None:
    again = _turn(_call("c3", "file_read_tool", {"paths": ["notes.txt"]}))
    _, agent = shipped_agent([LINK_THEN_READ, again, DONE], TOOLS, registered=TOOLS, checkpointer=InMemorySaver())

    with shipped_session(workspace):
        set_security_config(_asking_config(*_shell_allowed()))
        result = await agent.ainvoke({"messages": [HumanMessage(content="go")]}, THREAD)

    assert result["__interrupt__"], "the link to a credential file is now judged, and it asks"
    assert RAN == ["ln -s .env notes.txt"]
    assert DOTENV not in str(result["messages"])


async def test_the_pin_holds_across_an_approval_pause(workspace: Path) -> None:
    _, agent = shipped_agent([LINK_THEN_READ, DONE], TOOLS, registered=TOOLS, checkpointer=InMemorySaver())

    with shipped_session(workspace):
        set_security_config(_asking_config())
        paused = await agent.ainvoke({"messages": [HumanMessage(content="go")]}, THREAD)
        assert paused["__interrupt__"], "the shell command waits for the person"
        answers = _answers(await agent.ainvoke(Command(resume={"decisions": [{"type": "approve"}]}), THREAD))

    assert RAN == ["ln -s .env notes.txt"]
    assert answers["c2"].status == "error"
    assert DOTENV not in str(answers["c2"].content)


async def test_a_call_that_creates_the_file_a_later_call_names_does_not_move_it(workspace: Path) -> None:
    first = _turn(
        _call("c1", "bash_code_execute_tool", {"command": "touch fresh.txt"}),
        _call("c2", "file_read_tool", {"paths": ["fresh.txt"]}),
    )
    _, agent = shipped_agent([first, DONE], TOOLS, registered=TOOLS)

    with shipped_session(workspace):
        answers = _answers(await agent.ainvoke({"messages": [HumanMessage(content="go")]}))

    assert RAN == ["touch fresh.txt", "read"]
    assert answers["c2"].status == "success"
    assert _moved_calls() == []


async def test_a_rename_ahead_of_a_write_to_the_new_name_does_not_move_it(workspace: Path) -> None:
    (workspace / "draft.md").write_text("draft")
    first = _turn(
        _call("c1", "bash_code_execute_tool", {"command": "mv draft.md final.md"}),
        _call("c2", "file_write_tool", {"path": "final.md", "content": "final"}),
    )
    _, agent = shipped_agent([first, DONE], TOOLS, registered=TOOLS)

    with shipped_session(workspace):
        answers = _answers(await agent.ainvoke({"messages": [HumanMessage(content="go")]}))

    assert (workspace / "final.md").read_text() == "final"
    assert answers["c2"].status == "success"
    assert _moved_calls() == []


async def test_a_path_the_person_edited_on_the_card_is_not_held_to_the_path_that_was_judged(workspace: Path) -> None:
    (workspace / "ok.txt").write_text("fine")
    outside = workspace.parent / "elsewhere.txt"
    outside.write_text("outside")
    ask = _turn(_call("c1", "file_read_tool", {"paths": [str(outside)]}))
    _, agent = shipped_agent([ask, DONE], TOOLS, registered=TOOLS, checkpointer=InMemorySaver())

    with shipped_session(workspace):
        set_security_config(_asking_config())
        paused = await agent.ainvoke({"messages": [HumanMessage(content="go")]}, THREAD)
        assert paused["__interrupt__"], "a file outside the workspace waits for the person"
        edit = {"type": "edit", "args": {"paths": ["ok.txt"]}}
        answers = _answers(await agent.ainvoke(Command(resume={"decisions": [edit]}), THREAD))

    assert answers["c1"].status == "success"
    assert answers["c1"].content == "fine"
    assert _moved_calls() == []


async def test_a_read_of_a_file_nothing_changed_runs(workspace: Path) -> None:
    (workspace / "plan.md").write_text("plan")
    first = _turn(_call("c1", "file_read_tool", {"paths": ["plan.md"]}))
    _, agent = shipped_agent([first, DONE], TOOLS, registered=TOOLS)

    with shipped_session(workspace):
        answers = _answers(await agent.ainvoke({"messages": [HumanMessage(content="go")]}))

    assert answers["c1"].content == "plan"
    assert _moved_calls() == []
