"""Tests for the NOTE a ``[use skill]`` preload adds when the message cannot carry every skill the user named.

Covers:
- Each reason a named skill is left out is named in the NOTE: an unknown name, an SOP that cannot be read (the
  backend has none, it is empty, the loader raises) and the size budget
- One NOTE per message, between the header and the first SOP; none when every named skill was delivered
- A message in which no named skill can deliver an SOP is returned as typed, with or without the built-in skill
  tools: an agent that has them reads the tag under the ``[use <name>]`` rule of ``skill_select_tool``, one that
  does not receives the text as the user wrote it
- The NOTE sends the model to ``skill_select_tool`` only when the agent has the built-in skill tools
- The expanded message still passes the input guard, which screens the whole user message

What a preload delivers, and how a single skill degrades, is covered in test_explicit_skill_injection.py; what the
NOTE says in a real run without the built-in tools in test_no_builtin_tools_run.py.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from myrm_agent_harness.agent.meta_tools.skills.select import get_skill_document
from myrm_agent_harness.agent.skill_agent import SkillAgent
from myrm_agent_harness.backends.skills.protocols import SkillBackend
from myrm_agent_harness.backends.skills.types import SkillInstance, SkillMetadata
from myrm_agent_harness.core.security.detection.intent_router import scan_dangerous_intent
from myrm_agent_harness.core.security.detection.prompt_guard import scan_input
from tests.support.explicit_skill_stubs import StubSkillBackend, make_preload_agent, make_skill_metadata

_ALPHA = "# Alpha\n\nDo A."
# One SOP this size fills the whole preload budget on its own.
_BUDGET_FILLER = "# Big\n\n" + "x" * SkillAgent._TOKEN_BUDGET_MAX


def _agent(sops: dict[str, str], *listed: str, no_builtin_tools: bool = False) -> SkillAgent:
    """An agent whose backend lists ``listed`` and serves ``sops``; a listed skill without an SOP cannot be read."""
    skills = [make_skill_metadata(name=name, storage_skill_id=name) for name in listed]
    return make_preload_agent(
        skills=skills, backend=StubSkillBackend(content_map=sops), no_builtin_tools=no_builtin_tools
    )


def _note(query: str) -> str:
    """The one NOTE line of an expanded message."""
    (note,) = (line for line in query.split("\n") if line.startswith("[NOTE:"))
    return note


@pytest.mark.asyncio
async def test_an_unknown_name_is_named_as_not_found() -> None:
    agent = _agent({"alpha": _ALPHA}, "alpha")

    query, _, preloaded = await agent._preload_explicit_skill("[use alpha,ghost] go")

    assert "requested: ghost (not found)." in _note(query)
    assert [skill.name for skill in preloaded] == ["alpha"]


@pytest.mark.asyncio
@pytest.mark.parametrize("beta_sop", [None, ""], ids=["backend-has-none", "empty"])
async def test_a_skill_whose_sop_cannot_be_read_is_named_as_such(beta_sop: str | None) -> None:
    sops = {"alpha": _ALPHA} | ({} if beta_sop is None else {"beta": beta_sop})
    agent = _agent(sops, "alpha", "beta")

    query, _, preloaded = await agent._preload_explicit_skill("[use alpha,beta] go")

    assert "requested: beta (could not be read)." in _note(query)
    assert [skill.name for skill in preloaded] == ["alpha"]


@pytest.mark.asyncio
async def test_a_skill_whose_loader_raises_is_named_as_unreadable() -> None:
    agent = _agent({"alpha": _ALPHA, "beta": "# Beta\n\nDo B."}, "alpha", "beta")

    async def load(skill: SkillMetadata, backend: SkillBackend, *, skill_instance: SkillInstance | None = None) -> str:
        if skill.name == "beta":
            raise RuntimeError("loader failure")
        return await get_skill_document(skill, backend, skill_instance=skill_instance)

    with patch("myrm_agent_harness.agent.meta_tools.skills.select.get_skill_document", side_effect=load):
        query, _, preloaded = await agent._preload_explicit_skill("[use alpha,beta] go")

    assert "requested: beta (could not be read)." in _note(query)
    assert [skill.name for skill in preloaded] == ["alpha"]


@pytest.mark.asyncio
async def test_the_skill_that_breaks_the_budget_and_every_skill_after_it_are_named() -> None:
    agent = _agent({"alpha": _ALPHA, "big": _BUDGET_FILLER, "omega": "# Omega\n\nDo O."}, "alpha", "big", "omega")

    query, _, preloaded = await agent._preload_explicit_skill("[use alpha,big,omega] go")

    # ``omega`` would fit, but the preload stops at the first skill that does not.
    assert "requested: big (preload size budget reached), omega (preload size budget reached)." in _note(query)
    assert [skill.name for skill in preloaded] == ["alpha"]


@pytest.mark.asyncio
async def test_every_reason_is_listed_in_one_note() -> None:
    sops = {"alpha": _ALPHA, "big": _BUDGET_FILLER, "omega": "# Omega\n\nDo O."}
    agent = _agent(sops, "alpha", "unreadable", "big", "omega")

    query, _, _ = await agent._preload_explicit_skill("[use alpha,unreadable,big,omega,ghost] go")

    assert query.count("[NOTE:") == 1
    assert _note(query) == (
        "[NOTE: The user also requested: ghost (not found), unreadable (could not be read), "
        "big (preload size budget reached), omega (preload size budget reached). "
        "No SOP was preloaded for these skills. "
        "If the task needs one of them, load it with skill_select_tool; if it cannot be loaded, tell the user.]"
    )


@pytest.mark.asyncio
async def test_the_note_stands_between_the_header_and_the_first_sop() -> None:
    agent = _agent({"alpha": _ALPHA}, "alpha")

    query, _, _ = await agent._preload_explicit_skill("[use alpha,ghost] go")

    lines = query.split("\n")
    assert [lines[0][:11], lines[1][:6], lines[2], lines[3]] == ["[IMPORTANT:", "[NOTE:", "", "--- Skill: alpha ---"]
    assert lines[-1] == "go"


@pytest.mark.asyncio
async def test_a_message_that_carries_every_named_skill_has_no_note() -> None:
    agent = _agent({"alpha": _ALPHA, "beta": "# Beta\n\nDo B."}, "alpha", "beta")

    query, _, _ = await agent._preload_explicit_skill("[use alpha,beta] go")

    _header, *rest = query.split("\n")
    assert rest == [
        "",
        "--- Skill: alpha ---",
        "# Alpha",
        "",
        "Do A.",
        "--- Skill: beta ---",
        "# Beta",
        "",
        "Do B.",
        "",
        "go",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("no_builtin_tools", [False, True], ids=["built-in-tools", "no-built-in-tools"])
async def test_a_message_in_which_no_named_skill_delivers_an_sop_is_returned_as_typed(no_builtin_tools: bool) -> None:
    agent = _agent({}, "beta", no_builtin_tools=no_builtin_tools)

    result = await agent._preload_explicit_skill("[use beta,ghost] go")

    assert result == ("[use beta,ghost] go", None, [])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("no_builtin_tools", "names_the_tool"), [(False, True), (True, False)], ids=["built-in-tools", "no-built-in-tools"]
)
async def test_the_note_names_skill_select_tool_only_to_an_agent_that_has_it(
    no_builtin_tools: bool, names_the_tool: bool
) -> None:
    agent = _agent({"alpha": _ALPHA}, "alpha", no_builtin_tools=no_builtin_tools)

    query, _, _ = await agent._preload_explicit_skill("[use alpha,ghost] go")

    assert ("skill_select_tool" in _note(query)) is names_the_tool
    assert "tell the user" in _note(query)


@pytest.mark.asyncio
@pytest.mark.parametrize("no_builtin_tools", [False, True], ids=["built-in-tools", "no-built-in-tools"])
async def test_the_expanded_message_still_passes_the_input_guard(no_builtin_tools: bool) -> None:
    """The NOTE is part of the user's message, so its wording must not read as a forged system tag or an attack."""
    sops = {"alpha": _ALPHA, "big": _BUDGET_FILLER}
    agent = _agent(sops, "alpha", "unreadable", "big", no_builtin_tools=no_builtin_tools)

    query, _, _ = await agent._preload_explicit_skill("[use alpha,unreadable,big,ghost] go")

    assert "[NOTE:" in query
    assert scan_input(query).safe
    assert scan_dangerous_intent(query).safe
