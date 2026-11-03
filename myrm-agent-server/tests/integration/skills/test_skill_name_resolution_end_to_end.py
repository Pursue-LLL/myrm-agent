"""A skill name, written any way the catalog can resolve, through the real skill backend and the real agent loop.

[INPUT]
- app/core/skills/loader.py (POS: create_skill_backend, the catalog an agent runs with: seeded prebuilt skills plus enabled LOCAL skills)
- app/core/skills/prebuilt_sync.py (POS: seeds the prebuilt skills into storage)
- myrm_agent_harness.agent.skill_agent.SkillAgent (POS: the run loop; restores loaded skills from history and the session's names, reports them at turn end)
- myrm_agent_harness.agent.meta_tools.skills.select (POS: skill_select_tool, maps the name the model writes onto a catalog skill)

[OUTPUT]
- Tests that a typed name selects the skill the catalog lists under it, that a continued conversation restores the listed skill
  from its history and from the names the session recorded, and that a spelling two skills answer to selects neither.

[POS]
LOCAL skills are listed under ``xxx_skill`` runtime names while prebuilt skills keep their SKILL.md name, so a name the
model writes, or an older catalog left in a chat, may not be the name the catalog lists. The pieces' own tests stub their
neighbours; the crossing between harness and server is what this file runs for real. Only the model is scripted.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolCall, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.skill_agent import SkillAgent
from myrm_agent_harness.agent.skills.runtime.session_skills_rehydrate import SESSION_LOADED_SKILL_NAMES_CONTEXT_KEY
from myrm_agent_harness.agent.types import AgentRuntimeConfig
from myrm_agent_harness.backends.skills import SkillBackendProtocol
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from pydantic import Field

from app.core.skills import models as skill_models
from app.core.skills import prebuilt_sync
from app.core.skills.loader import create_skill_backend
from app.core.skills.store import reader
from app.core.skills.store.service import SkillsService

_PREBUILT = "deep-research"  # a prebuilt skill the catalog lists once
_LOCAL_ONLY = "my_local_tool_skill"  # runtime name of the LOCAL skill ``my-local-tool``
_TWIN_PREBUILT = "data-analysis"  # a prebuilt skill that a LOCAL copy shares its SKILL.md name with
_TWIN_LOCAL = "data_analysis_skill"  # runtime name of that LOCAL copy
_LOCAL_SOP_MARKER = "LOCAL-MARKER"
_LOCAL_SKILLS = (("my-local-tool", "my-local-tool"), ("data-analysis-clone", "data-analysis"))  # (directory, SKILL.md name)
_WRITE_BACK_TIMEOUT_S = 60.0
_ENTRY = re.compile(r'<skill_entry name="[^"]*" status="([^"]*)"')


@pytest.fixture(autouse=True)
def reset_sync_flag() -> Iterator[None]:
    prebuilt_sync._synced = False  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001


@dataclass(frozen=True)
class _Catalog:
    backend: SkillBackendProtocol
    skill_ids: list[str]
    skill_configs: dict[str, dict[str, object]]


@dataclass(frozen=True)
class _Turn:
    loaded_at_end: list[str]  # the skills the run reports at its end: what the server persists for the next turn
    select_text: str  # skill_select_tool's result; empty when the model made no call

    @property
    def entry_status(self) -> str | None:
        found = _ENTRY.search(self.select_text)
        return found.group(1) if found else None


def _select_call(typed_name: str) -> ToolCall:
    return ToolCall(
        name="skill_select_tool", args={"skill_names": [typed_name], "reason": "end-to-end"}, id="call_1", type="tool_call"
    )


class _SelectOnceModel(BaseChatModel):
    """Calls skill_select_tool once with ``typed_name`` while the conversation holds no tool result, then answers "ok"."""

    typed_name: str = ""
    tool_texts: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "select-once"

    def bind_tools(self, tools: object, **kwargs: object) -> _SelectOnceModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        results = [str(m.content) for m in messages if isinstance(m, ToolMessage)]
        self.tool_texts[:] = results
        if self.typed_name and not results:
            reply = AIMessage(content="", tool_calls=[_select_call(self.typed_name)])
        else:
            reply = AIMessage(content="ok")
        return ChatResult(generations=[ChatGeneration(message=reply)])


def _entry_head(name: str) -> str:
    """How a ready skill_select_tool result opens: the tool echoes the name the model wrote, not the listed one."""
    return f'<skill_entry name="{name}" status="ready">\n{name}：'


def _history_after_select(typed_name: str, select_text: str) -> list[BaseMessage]:
    """The chat a first turn leaves behind: the question, the model's select call, the tool's result, the answer."""
    return [
        HumanMessage(content="question"),
        AIMessage(content="", tool_calls=[_select_call(typed_name)]),
        ToolMessage(content=select_text, tool_call_id="call_1", name="skill_select_tool"),
        AIMessage(content="ok"),
    ]


class _Runner:
    """Runs one agent turn at a time over the catalog and reports what the run ended with."""

    def __init__(self, catalog: _Catalog, write_backs: asyncio.Queue[list[str]], workspaces_root: Path) -> None:
        self._catalog = catalog
        self._write_backs = write_backs
        self._workspaces_root = workspaces_root
        self._turns = 0

    async def turn(
        self,
        *,
        typed_name: str = "",
        history: list[BaseMessage] | None = None,
        recorded_names: list[str] | None = None,
    ) -> _Turn:
        """One turn: the model selects ``typed_name`` (when given) over ``history`` and the session's ``recorded_names``."""
        self._turns += 1
        number = self._turns
        model = _SelectOnceModel(typed_name=typed_name)
        agent = SkillAgent(
            llm=model,
            skill_backend=self._catalog.backend,
            skill_configs=self._catalog.skill_configs,
            desired_skill_ids=self._catalog.skill_ids,
            enable_memory_auto_extraction=False,
            enable_shell_tools=False,
            file_access_mode=FileAccessMode.NONE,
            config=AgentRuntimeConfig(),
        )
        context: dict[str, object] = {
            "chat_id": f"names-{number}",
            "session_id": f"chat_names_{number}",
            "workspaces_storage_root": str(self._workspaces_root),
        }
        if recorded_names is not None:
            context[SESSION_LOADED_SKILL_NAMES_CONTEXT_KEY] = recorded_names

        async def drain() -> None:
            async for _event in agent.run("question", chat_history=history, message_id=f"m-{number}", context=context):
                pass

        try:
            await asyncio.create_task(drain())  # a task of its own: every turn gets its own context-variable scope
            loaded_at_end = await asyncio.wait_for(self._write_backs.get(), timeout=_WRITE_BACK_TIMEOUT_S)
        finally:
            await agent.close()
        return _Turn(loaded_at_end=loaded_at_end, select_text=model.tool_texts[0] if model.tool_texts else "")


@pytest.fixture
async def catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Catalog:
    """Every seeded prebuilt skill plus two enabled LOCAL skills; no skill directory of the machine is read."""
    local_root = tmp_path / "local-skills"
    for dirname, name in _LOCAL_SKILLS:
        skill_dir = local_root / dirname
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: LOCAL skill of the end-to-end test ({name}).\n---\n\n# {_LOCAL_SOP_MARKER} {name}\n",
            encoding="utf-8",
        )

    storage = LocalStorageBackend(str(tmp_path / "storage"))
    service = SkillsService(storage=storage)
    monkeypatch.setattr("app.core.skills.store.service.skills_service", service)
    monkeypatch.setattr("app.core.skills.effective_skill_ids.skills_service", service)
    monkeypatch.setattr(skill_models, "DEFAULT_LOCAL_SKILL_PATHS", [])

    sync = await prebuilt_sync.sync_prebuilt_seeds(storage)
    config = await service.user_config.get_config()
    config.enabled_prebuilt_ids = list(sync.skill_ids)
    config.local_skill_paths = [str(local_root)]
    await service.user_config.save_config(config)
    local_ids = sorted(skill.id for skill in await reader.list_local_skills(service.user_config))
    config = await service.user_config.get_config()
    config.enabled_local_skill_ids = local_ids
    await service.user_config.save_config(config)

    skill_ids = sorted(sync.skill_ids) + local_ids
    backend = await create_skill_backend(
        storage=storage, skill_ids=skill_ids, user_id="default", allowed_prebuilt_ids=frozenset(sync.skill_ids)
    )
    skills = await backend.load_skills(skill_ids)
    listed = {skill.name for skill in skills}
    assert {_PREBUILT, _TWIN_PREBUILT, _TWIN_LOCAL, _LOCAL_ONLY} <= listed, (
        "the catalog no longer lists these names; the spellings below encode that naming, update them with it"
    )
    return _Catalog(
        backend=backend,
        skill_ids=skill_ids,
        skill_configs={(skill.storage_skill_id or skill.name): {"is_core": False} for skill in skills},
    )


@pytest.fixture
async def runner(catalog: _Catalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Runner:
    write_backs: asyncio.Queue[list[str]] = asyncio.Queue()

    async def report_instead_of_persisting(
        self: SkillAgent,
        query: object,
        chat_history: object,
        assistant_chunks: object,
        active_skills: list[str],
        run_chat_id: str | None = None,
    ) -> None:
        write_backs.put_nowait(list(active_skills))

    monkeypatch.setattr(SkillAgent, "_cleanup_session", report_instead_of_persisting)
    return _Runner(catalog, write_backs, tmp_path / "workspaces")


async def test_every_spelling_of_a_prebuilt_name_loads_the_skill_the_catalog_lists(runner: _Runner) -> None:
    exact = await runner.turn(typed_name=_PREBUILT)
    assert exact.entry_status == "ready"
    assert exact.loaded_at_end == [_PREBUILT]

    for spelling in ("deep_research_skill", "Deep-Research", "deep_research", " deep-research "):
        turn = await runner.turn(typed_name=spelling)
        assert turn.loaded_at_end == [_PREBUILT], spelling
        # It is the SOP the exact name loads; only the name the tool echoes is the one the model wrote.
        assert turn.select_text == exact.select_text.replace(_entry_head(_PREBUILT), _entry_head(spelling), 1), spelling


async def test_every_spelling_of_a_local_name_loads_the_skill_listed_under_its_runtime_name(runner: _Runner) -> None:
    for spelling in (_LOCAL_ONLY, "my-local-tool", "my_local_tool"):
        turn = await runner.turn(typed_name=spelling)
        assert turn.entry_status == "ready", spelling
        assert turn.loaded_at_end == [_LOCAL_ONLY], spelling
        assert f"{_LOCAL_SOP_MARKER} my-local-tool" in turn.select_text, spelling


async def test_a_local_copy_of_a_prebuilt_skill_leaves_both_selectable_and_is_never_guessed_between(runner: _Runner) -> None:
    prebuilt = await runner.turn(typed_name=_TWIN_PREBUILT)
    assert (prebuilt.entry_status, prebuilt.loaded_at_end) == ("ready", [_TWIN_PREBUILT])
    assert _LOCAL_SOP_MARKER not in prebuilt.select_text

    local_copy = await runner.turn(typed_name=_TWIN_LOCAL)
    assert (local_copy.entry_status, local_copy.loaded_at_end) == ("ready", [_TWIN_LOCAL])
    assert f"{_LOCAL_SOP_MARKER} data-analysis" in local_copy.select_text

    for ambiguous in ("data_analysis", "Data-Analysis"):  # both skills answer to these
        turn = await runner.turn(typed_name=ambiguous)
        assert (turn.entry_status, turn.loaded_at_end) == ("error", []), ambiguous
        assert _LOCAL_SOP_MARKER not in turn.select_text, ambiguous


async def test_a_continued_conversation_restores_the_skill_its_history_selected_under_another_name(runner: _Runner) -> None:
    for written, listed in (("deep_research_skill", _PREBUILT), ("my-local-tool", _LOCAL_ONLY)):
        first = await runner.turn(typed_name=written)
        second = await runner.turn(history=_history_after_select(written, first.select_text))
        assert second.loaded_at_end == [listed], written


async def test_the_names_a_session_recorded_restore_the_skills_the_catalog_lists_under_them(runner: _Runner) -> None:
    listed_for_recorded: dict[str, list[str]] = {
        "deep_research_skill": [_PREBUILT],  # an older catalog's runtime name
        _PREBUILT: [_PREBUILT],
        "my-local-tool": [_LOCAL_ONLY],
        _LOCAL_ONLY: [_LOCAL_ONLY],
        _TWIN_PREBUILT: [_TWIN_PREBUILT],
        _TWIN_LOCAL: [_TWIN_LOCAL],
        "data_analysis": [],  # both skills answer to it: neither is restored
    }
    for recorded, listed in listed_for_recorded.items():
        turn = await runner.turn(recorded_names=[recorded])
        assert turn.loaded_at_end == listed, recorded
