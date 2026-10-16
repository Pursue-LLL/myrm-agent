"""Sub-agents delegated from an incognito chat must not open the user's memory.

The parent chat promises that no memory is read or written. A delegated custom agent that opened its own memory
manager would search the stored memories and, through end-of-session extraction, write new ones. The sub-agent
cannot see the chat's flag (its parent is the runtime agent, not the chat wrapper), so the owner of the chat tells
the catalog, and these tests follow the production path from the catalog to the built agent.
"""

import ast
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.agent.sub_agents.types import MemoryIsolationPolicy

from app.ai_agents.custom_agent_factory import CustomAgentFactory
from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

AGENT_ID = "custom-researcher"


@asynccontextmanager
async def _session() -> AsyncIterator[None]:
    yield None


@pytest.fixture(autouse=True)
def stored_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = SimpleNamespace(
        id=AGENT_ID,
        display_name="Researcher",
        description="",
        system_prompt="Research.",
        model=None,
        max_iterations=8,
        skills=[],
        enabled_builtin_tools=(),
        memory_policy=None,
        metadata={},
    )
    monkeypatch.setattr("app.ai_agents.subagent_catalog.get_session_factory", lambda: _session)
    monkeypatch.setattr("app.ai_agents.subagent_catalog.AgentService.get_agent_by_id", AsyncMock(return_value=profile))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("incognito_mode", "isolation"),
    [(False, MemoryIsolationPolicy.READ_ONLY_GLOBAL), (True, MemoryIsolationPolicy.EPHEMERAL_SESSION)],
)
async def test_database_agents_are_isolated_from_memory_according_to_the_chat(
    incognito_mode: bool, isolation: MemoryIsolationPolicy
) -> None:
    config = await DatabaseSubagentCatalog(incognito_mode=incognito_mode).resolve(AGENT_ID)

    assert config is not None
    assert config.memory_isolation is isolation


@pytest.mark.asyncio
@pytest.mark.parametrize(("incognito_mode", "gets_memory"), [(False, True), (True, False)])
async def test_a_delegated_custom_agent_gets_a_memory_manager_only_in_a_chat_that_is_not_incognito(
    monkeypatch: pytest.MonkeyPatch, incognito_mode: bool, gets_memory: bool
) -> None:
    import myrm_agent_harness.api as api_module

    manager = SimpleNamespace(name="memory-manager")
    create_memory_manager = AsyncMock(return_value=manager)
    create_skill_agent = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr("app.core.memory.adapters.setup.create_memory_manager", create_memory_manager)
    monkeypatch.setattr(
        "app.services.agent.platform_config.load_platform_retrieval_configs",
        AsyncMock(return_value=(SimpleNamespace(), None)),
    )
    monkeypatch.setattr(
        "app.services.memory.extract_retry.resolve_chat_extraction_llm.get_platform_dedup_llm",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(api_module, "create_skill_agent", create_skill_agent)
    monkeypatch.setattr("app.platform_utils.get_storage_provider", lambda: SimpleNamespace())
    monkeypatch.setattr(CustomAgentFactory, "_ensure_initialized", AsyncMock())

    config = await DatabaseSubagentCatalog(incognito_mode=incognito_mode).resolve(AGENT_ID)
    assert config is not None and config.agent_factory is not None
    # The real parent is the runtime agent, which carries no incognito flag at all.
    parent = SimpleNamespace(llm=SimpleNamespace(), executor=None, _last_context={"chat_id": "chat-1"})

    await config.agent_factory.build(config, [], "task", parent, current_depth=1)

    assert create_memory_manager.await_count == int(gets_memory)
    assert create_skill_agent.await_args is not None
    assert create_skill_agent.await_args.kwargs["memory_manager"] is (manager if gets_memory else None)


# Unattended post-run verification belongs to no chat, so there is no incognito flag to pass on.
_CATALOG_SITES_WITHOUT_A_CHAT = {"app/core/cron/adapters/post_run_verification.py"}
_CATALOG_CONSUMERS = {"DatabaseSubagentCatalog", "SubagentManagementExtension"}


def _passes_the_chats_flag(call: ast.Call) -> bool:
    """True when the call hands over a computed `incognito_mode`; a literal such as `False` would defeat the guard."""
    return any(keyword.arg == "incognito_mode" and not isinstance(keyword.value, ast.Constant) for keyword in call.keywords)


def _called_name(call: ast.Call) -> str | None:
    """The class name of `Name(...)` and `module.Name(...)`; an import alias cannot be followed."""
    if isinstance(call.func, ast.Name):
        return call.func.id
    return call.func.attr if isinstance(call.func, ast.Attribute) else None


def _consumer_calls_missing_the_flag(app_dir: Path) -> list[str]:
    missing: list[str] = []
    for source in app_dir.rglob("*.py"):
        relative = source.relative_to(app_dir.parent).as_posix()
        if relative in _CATALOG_SITES_WITHOUT_A_CHAT:
            continue
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and _called_name(node) in _CATALOG_CONSUMERS and not _passes_the_chats_flag(node):
                missing.append(f"{relative}:{node.lineno}")
    return missing


def test_every_chat_bound_catalog_site_passes_the_incognito_flag() -> None:
    """A new place that builds a catalog for a chat must pass the chat's flag instead of silently defaulting."""
    assert _consumer_calls_missing_the_flag(Path(__file__).resolve().parents[2] / "app") == []


@pytest.mark.parametrize(
    "call",
    [
        "DatabaseSubagentCatalog()",
        "DatabaseSubagentCatalog(incognito_mode=False)",
        "catalog_module.DatabaseSubagentCatalog()",
        "SubagentManagementExtension(incognito_mode=True)",
        "SubagentManagementExtension(**options)",
    ],
)
def test_the_guard_rejects_a_missing_or_literal_flag(tmp_path: Path, call: str) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "site.py").write_text(f"{call}\n", encoding="utf-8")

    assert _consumer_calls_missing_the_flag(app_dir) == ["app/site.py:1"]


def test_the_guard_accepts_a_computed_flag(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "site.py").write_text("DatabaseSubagentCatalog(incognito_mode=params.incognito_mode)\n", encoding="utf-8")

    assert _consumer_calls_missing_the_flag(app_dir) == []
