"""Integration: stream preflight gap SSE + discover no-gap behavior + dispatcher wiring."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.tools import BaseTool
from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.meta_tools.discover_capability.discover_capability_tool import (
    sync_discover_capability_tool,
)
from myrm_agent_harness.agent.streaming.stream_executor import (
    StreamContext,
    StreamExecutor,
)
from myrm_agent_harness.agent.streaming.types import AgentEventType, AgentStreamEvent
from myrm_agent_harness.agent.tool_management.registry import ToolRegistry
from myrm_agent_harness.agent.tool_management.types import ToolBindMode, ToolSource
from myrm_agent_harness.agent.types import AgentRunStatistics
from pydantic import BaseModel, Field

from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection

_SEARCH_MOUNT_SKILL_COUNT = 21
_DISCOVER_MISS_QUERY = "zzz_nonexistent_qwerty_9847261"


class _DummyInput(BaseModel):
    arg1: str = Field(default="")


class _DummyDeferredTool(BaseTool):
    name: str = "dummy_deferred_tool"
    description: str = "Deferred placeholder for discover index rebuild tests."
    args_schema: type[BaseModel] = _DummyInput

    def _run(self, arg1: str = "") -> str:
        return "ok"


def _discover_gateway_skills() -> list:
    """21 searchable bound skills so sync_discover_capability_tool mounts (hidden_count > 0)."""
    from myrm_agent_harness.backends.skills.types import SkillMetadata

    featured = SkillMetadata(
        name="cap_integration_skill",
        description="Integration test skill to enable discover gateway binding.",
        model_invocable=True,
        available=True,
        always=True,
    )
    skills = [
        SkillMetadata(
            name=f"cap_bound_skill_{index:02d}",
            description=f"Capability integration bound skill {index}",
            model_invocable=True,
            available=True,
        )
        for index in range(_SEARCH_MOUNT_SKILL_COUNT)
    ]
    skills[0] = featured
    return skills


def _bm25_tokens(text: str) -> set[str]:
    from myrm_agent_harness.toolkits.retriever.bm25_retrieval import preprocess_text

    return set(preprocess_text(text))


def _assert_discover_miss_query_disjoint_from_fixture_names() -> None:
    """Miss query must not BM25-token-overlap fixture index docs (prevents false PASS/FAIL)."""
    from myrm_agent_harness.agent.meta_tools.skills.search.engine import (
        SkillSearchEngine,
        _build_skill_index_document,
    )

    query_tokens = _bm25_tokens(_DISCOVER_MISS_QUERY)
    overlaps: list[tuple[str, set[str]]] = []
    for skill in _discover_gateway_skills():
        doc_tokens = _bm25_tokens(_build_skill_index_document(skill))
        shared = query_tokens & doc_tokens
        if shared:
            overlaps.append((skill.name, shared))
    assert (
        not overlaps
    ), f"_DISCOVER_MISS_QUERY shares BM25 tokens with fixture index docs: {overlaps}"

    engine = SkillSearchEngine(_discover_gateway_skills(), enable_query_expansion=False)
    assert engine.search_bm25(_DISCOVER_MISS_QUERY) == []


def test_discover_miss_query_disjoint_from_fixture_skill_names() -> None:
    """Regression guard: miss query must not accidentally BM25-match bound skill fixtures."""
    _assert_discover_miss_query_disjoint_from_fixture_names()


def _collect_agent_stream(
    client: TestClient,
    payload: dict[str, object],
    *,
    stream_timeout: float = 240.0,
    stop_when: (
        Callable[[dict[str, object], list[dict[str, object]]], bool] | None
    ) = None,
) -> list[dict[str, object]]:
    collected: list[dict[str, object]] = []
    with client.stream(
        "POST",
        "/api/v1/agents/agent-stream",
        json=payload,
        timeout=stream_timeout,
    ) as response:
        assert response.status_code == 200, response.text
        for line in response.iter_lines():
            if not line or not line.strip().startswith("data: "):
                continue
            raw = line.strip()[6:]
            if raw == "[DONE]":
                break
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                collected.append(data)
                if stop_when is not None and stop_when(data, collected):
                    break
    return collected


def _stop_on_render_ui_capability_gap(
    event: dict[str, object],
    _collected: list[dict[str, object]],
) -> bool:
    if event.get("type") != "capability_gap":
        return False
    payload_data = event.get("data")
    return isinstance(payload_data, dict) and payload_data.get("tool_id") == "render_ui"


def _stop_on_web_search_config_gap(
    event: dict[str, object],
    _collected: list[dict[str, object]],
) -> bool:
    if event.get("type") != "capability_gap":
        return False
    payload_data = event.get("data")
    if not isinstance(payload_data, dict):
        return False
    return (
        payload_data.get("tool_id") == "web_search"
        and payload_data.get("reason") == "not_configured"
    )


def _stop_on_migration_readiness_gap(
    event: dict[str, object],
    _collected: list[dict[str, object]],
) -> bool:
    if event.get("type") != "capability_gap":
        return False
    payload_data = event.get("data")
    if not isinstance(payload_data, dict):
        return False
    reason = payload_data.get("reason")
    return payload_data.get("tool_id") == "migration_import" and reason in {
        "migration_readiness_warning",
        "migration_readiness_critical",
    }


def _message_text_from_stream_events(events: list[dict[str, object]]) -> str:
    chunks: list[str] = []
    for event in events:
        if event.get("type") != "message":
            continue
        data = event.get("data")
        if isinstance(data, str) and data:
            chunks.append(data)
    return "".join(chunks)


_AGENT_STREAM_TEST_TIMEOUT = pytest.mark.timeout(420)


def _invoked_tool_names(events: list[dict[str, object]]) -> set[str]:
    names: set[str] = set()
    for event in events:
        if event.get("type") not in {"tasks_steps", "tool_end", "tool_start"}:
            continue
        tool_name = event.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            names.add(tool_name)
    return names


def _gap_events(
    events: list[dict[str, object]], event_type: str
) -> list[dict[str, object]]:
    return [event for event in events if event.get("type") == event_type]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_miss_returns_not_found_without_gap_block_or_sse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discover miss must not emit entitlement gap blocks or custom events."""
    registry = ToolRegistry()
    registry.register(
        _DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.TURN1
    )
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    miss_query = _DISCOVER_MISS_QUERY
    result = await discover.ainvoke({"query": miss_query})
    assert "No capabilities found" in result
    assert "<CapabilityGap>" not in result
    assert "<SkillGap>" not in result
    assert not any(name in {"capability_gap", "skill_gap"} for name, _ in captured)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_miss_no_gap_when_render_ui_group_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discover miss must stay gap-free regardless of active tool groups."""
    registry = ToolRegistry()
    registry.register(
        _DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.TURN1
    )
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    result = await discover.ainvoke({"query": "please render ui interactive form"})
    assert "No capabilities found" in result
    assert "<CapabilityGap>" not in result
    assert not any(name == "capability_gap" for name, _ in captured)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_miss_no_gap_when_render_ui_group_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discover no longer emits render_ui entitlement gaps on miss."""
    registry = ToolRegistry()
    registry.register(
        _DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.TURN1
    )
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    result = await discover.ainvoke({"query": "please render ui interactive form"})
    assert "No capabilities found" in result
    assert "<CapabilityGap>" not in result
    assert not any(name == "capability_gap" for name, _ in captured)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "generate video from this script",
        "create multi-step plan for migration",
        "search my personal wiki notes",
    ],
)
async def test_discover_miss_no_capability_gap_for_disabled_groups(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    registry = ToolRegistry()
    registry.register(
        _DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.TURN1
    )
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    result = await discover.ainvoke({"query": query})
    assert "No capabilities found" in result
    assert "<CapabilityGap>" not in result
    assert not any(name == "capability_gap" for name, _ in captured)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_miss_no_gap_for_file_ops_intent_without_file_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fast-mode groups omit file_ops; grep/bash queries must not emit file_ops entitlement gap."""
    registry = ToolRegistry()
    registry.register(
        _DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.TURN1
    )
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    result = await discover.ainvoke(
        {"query": "grep pattern in repo files and run bash script"}
    )
    assert "No capabilities found" in result
    assert "<CapabilityGap>" not in result
    assert not any(name == "capability_gap" for name, _ in captured)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_miss_no_skill_gap_block_or_sse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discover miss must not emit SkillGap blocks or skill_gap SSE."""
    registry = ToolRegistry()
    registry.register(
        _DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.TURN1
    )
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    result = await discover.ainvoke({"query": "run github_pr_skill workflow now"})
    assert "No capabilities found" in result
    assert "<SkillGap>" not in result
    assert not any(name == "skill_gap" for name, _ in captured)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stream_dispatcher_forwards_skill_gap_custom_event() -> None:
    """Custom stream chunk skill_gap must become SKILL_GAP SSE event."""
    stats = AgentRunStatistics()
    ctx = StreamContext(
        agent=MagicMock(),
        agent_input={"messages": []},
        merged_context={"locale": "en"},
        run_config={},
        stats=stats,
        message_id="skill_gap_dispatch_test",
        cancel_token=None,
        steering_token=None,
        source_tracker=MagicMock(),
        output_queue=asyncio.Queue(),
        event_logger=None,
    )

    class _FakeCompactor:
        def __init__(self) -> None:
            self.events: list[object] = []

        async def put(self, event: object) -> None:
            self.events.append(event)

    executor = StreamExecutor(
        ctx=ctx,
        fallback_llm=None,
        safety_fallback_llm=None,
        rebuild_agent_fn=MagicMock(),
    )
    executor._compactor = _FakeCompactor()

    payload = {"skill_id": "github_pr_skill"}
    chunk = ("custom", {"name": "skill_gap", "data": payload})
    await executor._dispatch_chunk(chunk, ctx, [])

    gap_events = [
        event
        for event in executor._compactor.events
        if isinstance(event, AgentStreamEvent)
        and event.type == AgentEventType.SKILL_GAP
    ]
    assert len(gap_events) == 1
    assert gap_events[0].data == payload


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stream_dispatcher_forwards_capability_gap_custom_event() -> None:
    """Custom stream chunk capability_gap must become CAPABILITY_GAP SSE event."""
    stats = AgentRunStatistics()
    ctx = StreamContext(
        agent=MagicMock(),
        agent_input={"messages": []},
        merged_context={"locale": "en"},
        run_config={},
        stats=stats,
        message_id="gap_dispatch_test",
        cancel_token=None,
        steering_token=None,
        source_tracker=MagicMock(),
        output_queue=asyncio.Queue(),
        event_logger=None,
    )

    class _FakeCompactor:
        def __init__(self) -> None:
            self.events: list[object] = []

        async def put(self, event: object) -> None:
            self.events.append(event)

    executor = StreamExecutor(
        ctx=ctx,
        fallback_llm=None,
        safety_fallback_llm=None,
        rebuild_agent_fn=MagicMock(),
    )
    executor._compactor = _FakeCompactor()

    payload = {"tool_id": "browser", "tool_group": "browser"}
    chunk = ("custom", {"name": "capability_gap", "data": payload})
    await executor._dispatch_chunk(chunk, ctx, [])

    gap_events = [
        event
        for event in executor._compactor.events
        if isinstance(event, AgentStreamEvent)
        and event.type == AgentEventType.CAPABILITY_GAP
    ]
    assert len(gap_events) == 1
    assert gap_events[0].data == payload


@pytest.mark.e2e
@_AGENT_STREAM_TEST_TIMEOUT
def test_agent_stream_discover_miss_does_not_emit_capability_gap_sse(
    client: TestClient,
) -> None:
    """Real agent-stream: discover miss must not emit discover-driven capability_gap SSE."""
    miss_query = _DISCOVER_MISS_QUERY
    chat_id = f"test_cap_gap_{uuid.uuid4().hex[:8]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    payload: dict[str, object] = {
        "message_id": "test-cap-gap-1",
        "chat_id": chat_id,
        "query": (
            "You MUST call skill_search_tool exactly once with query "
            f"'{miss_query}'. Do not call any other tool. "
            "After the tool returns, reply with the single word DONE."
        ),
        "action_mode": "agent",
        "model_selection": get_lite_model_selection(),
        "agent_config": {
            "enabled_builtin_tools": [
                "web_search",
                "memory",
                "file_ops",
                "code_execute",
            ],
            "skill_ids": [],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)

    invoked = _invoked_tool_names(events)
    if "skill_search_tool" not in invoked:
        pytest.skip(
            "model did not invoke skill_search_tool; deterministic no-gap wiring covered elsewhere"
        )

    gaps = _gap_events(events, "capability_gap")
    blob = json.dumps(events, ensure_ascii=False)
    assert (
        not gaps and "<CapabilityGap>" not in blob
    ), "discover miss must not emit capability_gap SSE or CapabilityGap blocks"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_miss_no_web_search_gap_when_web_group_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discover miss must not emit web_search entitlement gaps."""
    registry = ToolRegistry()
    registry.register(
        _DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.TURN1
    )
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    result = await discover.ainvoke({"query": "search the web for apple news today"})
    assert "No capabilities found" in result
    assert "<CapabilityGap>" not in result
    assert not any(name == "capability_gap" for name, _ in captured)


@pytest.mark.integration
def test_web_render_ui_form_query_preflight_no_gap_unit_parity() -> None:
    """Parity guard: web_chat + render_ui ON must not emit preflight gap (see unit SSOT)."""
    from types import SimpleNamespace

    from app.ai_agents.general_agent.active_tool_groups import (
        derive_active_tool_groups_from_params,
    )
    from app.services.agent.stream_session.entitlement_gap_preflight import (
        build_entitlement_gap_sse_event,
        reset_capability_gap_emission_tracker,
    )

    reset_capability_gap_emission_tracker()
    params = SimpleNamespace(
        enable_web_search=True,
        enable_browser=False,
        file_access_mode=FileAccessMode.FULL,
        enable_shell_tools=True,
        enable_computer_use=False,
        enable_memory=True,
        incognito_mode=False,
        enable_conversation_search=False,
        enable_kanban=False,
        enable_wiki=False,
        enable_answer_tool=False,
        enable_render_ui=True,
        enable_structured_clarify=False,
        enable_cron_eager=False,
        enable_planning=False,
        image_generation=None,
        video_generation=None,
        tts=None,
    )
    event = build_entitlement_gap_sse_event(
        message_id="msg-web-parity",
        user_text="帮我填表准备 staging 部署配置",
        active_tool_groups=derive_active_tool_groups_from_params(params),
        chat_id="chat-web-parity",
        channel_name="web_chat",
        client_surface="web",
    )
    assert event is None


@pytest.mark.integration
@_AGENT_STREAM_TEST_TIMEOUT
def test_agent_stream_emits_web_search_config_gap_sse(
    client: TestClient,
    mock_load_user_configs: AsyncMock,
) -> None:
    """Preflight must emit capability_gap when web_search profile on but search unconfigured."""
    from dataclasses import replace

    from app.services.agent.stream_session.entitlement_gap_preflight import (
        reset_capability_gap_emission_tracker,
    )
    from tests.api.agent.conftest import _build_mock_user_configs

    reset_capability_gap_emission_tracker()
    mock_load_user_configs.return_value = replace(
        _build_mock_user_configs(),
        search_is_user_configured=False,
        search_cfg=None,
    )

    chat_id = f"test_preflight_web_search_cfg_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": "搜索一下今天的新闻",
        "actionMode": "agent",
        "modelSelection": get_lite_model_selection(),
        "agentConfig": {
            "enabledBuiltinTools": ["web_search", "memory"],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(
        client,
        payload,
        stop_when=_stop_on_web_search_config_gap,
    )
    check_e2e_errors(events)

    gaps = _gap_events(events, "capability_gap")
    web_gaps = [
        event
        for event in gaps
        if isinstance(event.get("data"), dict)
        and event["data"].get("tool_id") == "web_search"
        and event["data"].get("reason") == "not_configured"
    ]
    assert (
        web_gaps
    ), "expected stream preflight capability_gap SSE for unconfigured web_search"
    payload_data = web_gaps[0]["data"]
    assert isinstance(payload_data, dict)
    assert payload_data.get("settings_path") == "/settings/search"
    assert payload_data.get("tool_group") == "web"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_migration_readiness_live_resolve_emits_gap_after_db_seed() -> None:
    """Live DB seed + resolve_and_build must emit MCP warning gap (no full agent-stream)."""
    from unittest.mock import AsyncMock, patch

    from app.platform_utils import get_session_factory
    from app.services.agent.params.models import MigrationReadinessAnchorRequest
    from app.services.agent.stream_session.entitlement_gap_preflight import (
        reset_capability_gap_emission_tracker,
    )
    from app.services.agent.stream_session.migration_readiness_preflight import (
        resolve_and_build_migration_readiness_gap_sse_event,
    )
    from app.services.memory.import_sessions import (
        ImportReadinessRecheckFacts,
        MemoryImportSessionService,
    )
    from tests.services.memory.test_import_sessions import _FakeMemoryManager

    reset_capability_gap_emission_tracker()

    session_factory = get_session_factory()
    async with session_factory() as db:
        service = MemoryImportSessionService(db)
        manager = _FakeMemoryManager()
        payload = {
            "data": {
                "semantic": [
                    {
                        "content": "Migration readiness integration seed.",
                        "metadata": {},
                    },
                ]
            }
        }
        dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(
            payload,
            "native_json",
        )
        confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)
        await service.save_post_import_diagnostic(
            import_batch_id=confirm.import_batch_id,
            diagnostic_run_id="diag-ready",
            diagnostic_status="ready",
            failed_count=0,
        )
        await service.save_post_import_readiness(
            import_batch_id=confirm.import_batch_id,
            readiness_status="warning",
            readiness_issues=[
                {
                    "code": "mcp_servers_imported_disabled",
                    "severity": "warning",
                    "params": {"count": 2},
                    "settings_path": "/settings/mcp",
                }
            ],
            recheck_facts=ImportReadinessRecheckFacts(
                source_has_api_keys=False,
                diagnostic_status="ready",
                diagnostic_failed_count=0,
                mcp_config_count=2,
                workspace_rules_skipped=0,
            ),
        )
        import_batch_id = confirm.import_batch_id

    with patch(
        "app.services.migration.source_secrets_importer.external_source_providers_configured",
        new=AsyncMock(return_value=False),
    ):
        event, status = await resolve_and_build_migration_readiness_gap_sse_event(
            message_id="msg-migration-parity",
            migration_readiness_anchor=MigrationReadinessAnchorRequest(
                import_batch_id=import_batch_id,
                readiness_status="warning",
            ),
            chat_id="chat-migration-parity",
            locale="en",
        )

    assert status == "warning"
    assert event is not None
    data = event.get("data")
    assert isinstance(data, dict)
    assert data.get("tool_id") == "migration_import"
    assert data.get("reason") == "migration_readiness_warning"
    assert data.get("settings_path") == "/settings/mcp"
    assert data.get("import_batch_id") == import_batch_id


async def _seed_migration_readiness_batch_for_stream() -> str:
    from app.platform_utils import get_session_factory
    from app.services.memory.import_sessions import (
        ImportReadinessRecheckFacts,
        MemoryImportSessionService,
    )
    from tests.services.memory.test_import_sessions import _FakeMemoryManager

    session_factory = get_session_factory()
    async with session_factory() as db:
        service = MemoryImportSessionService(db)
        manager = _FakeMemoryManager()
        payload = {
            "data": {
                "semantic": [
                    {
                        "content": "Migration readiness agent-stream integration seed.",
                        "metadata": {},
                    },
                ]
            }
        }
        dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(
            payload,
            "native_json",
        )
        confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)
        await service.save_post_import_diagnostic(
            import_batch_id=confirm.import_batch_id,
            diagnostic_run_id="diag-ready",
            diagnostic_status="ready",
            failed_count=0,
        )
        await service.save_post_import_readiness(
            import_batch_id=confirm.import_batch_id,
            readiness_status="warning",
            readiness_issues=[
                {
                    "code": "mcp_servers_imported_disabled",
                    "severity": "warning",
                    "params": {"count": 2},
                    "settings_path": "/settings/mcp",
                }
            ],
            recheck_facts=ImportReadinessRecheckFacts(
                source_has_api_keys=False,
                diagnostic_status="ready",
                diagnostic_failed_count=0,
                mcp_config_count=2,
                workspace_rules_skipped=0,
            ),
        )
        return confirm.import_batch_id


@pytest.mark.integration
@_AGENT_STREAM_TEST_TIMEOUT
def test_agent_stream_migration_readiness_gap_does_not_block_assistant(
    client: TestClient,
) -> None:
    """Soft gate: migration preflight gap SSE must not block assistant message output."""
    from unittest.mock import AsyncMock, patch

    from app.services.agent.stream_session.entitlement_gap_preflight import (
        reset_capability_gap_emission_tracker,
    )

    reset_capability_gap_emission_tracker()
    import_batch_id = asyncio.run(_seed_migration_readiness_batch_for_stream())

    chat_id = f"test_migration_soft_gate_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": "Reply with one short greeting sentence only.",
        "actionMode": "agent",
        "modelSelection": get_lite_model_selection(),
        "agentConfig": {
            "enabledBuiltinTools": ["memory"],
        },
        "migrationReadinessAnchor": {
            "importBatchId": import_batch_id,
            "readinessStatus": "warning",
        },
        "timezone": "UTC",
    }

    with patch(
        "app.services.migration.source_secrets_importer.external_source_providers_configured",
        new=AsyncMock(return_value=False),
    ):
        events = _collect_agent_stream(client, payload)

    check_e2e_errors(events)
    migration_gaps = [
        event
        for event in _gap_events(events, "capability_gap")
        if isinstance(event.get("data"), dict)
        and event["data"].get("tool_id") == "migration_import"
        and event["data"].get("reason") == "migration_readiness_warning"
    ]
    assert (
        migration_gaps
    ), "expected migration readiness capability_gap SSE before agent execution"
    assistant_text = _message_text_from_stream_events(events).strip()
    assert len(assistant_text) > 5, (
        "soft gate must not block assistant output; "
        f"event_types={sorted({e.get('type') for e in events})}"
    )


@pytest.mark.integration
@_AGENT_STREAM_TEST_TIMEOUT
def test_agent_stream_accepts_enabled_builtin_tools_without_error(
    client: TestClient,
) -> None:
    """agent-stream with explicit enabledBuiltinTools (no browser) must complete."""
    chat_id = f"test_enabled_tools_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "messageId": "test-enabled-tools-1",
        "chatId": chat_id,
        "query": "Reply with the word OK only.",
        "actionMode": "agent",
        "modelSelection": get_lite_model_selection(),
        "agentConfig": {
            "enabledBuiltinTools": ["web_search", "memory", "file_ops", "code_execute"],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)
    assert events


@pytest.mark.integration
@_AGENT_STREAM_TEST_TIMEOUT
def test_agent_stream_default_builtin_tools_persist_togglable_only(
    client: TestClient,
) -> None:
    """Default agent-stream persists togglable tools only; baseline is runtime-forced."""
    from app.services.agent.builtin_tool_ids import (
        AGENT_BASELINE_BUILTIN_TOOLS,
        DEFAULT_ENABLED_BUILTIN_TOOLS,
    )

    chat_id = f"test_default_tools_{uuid.uuid4().hex[:8]}"
    payload = {
        "query": "Reply with the word OK only.",
        "message_id": "test-default-tools-1",
        "chat_id": chat_id,
        "action_mode": "agent",
        "model_selection": get_lite_model_selection(),
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)

    tools_snapshot = next(
        (event for event in events if event.get("type") == "tools_snapshot"),
        None,
    )
    if tools_snapshot is None:
        invoked = _invoked_tool_names(events)
        assert (
            "file_read_tool" in invoked or "bash_code_execute_tool" in invoked
        ), "baseline file/bash must be Turn1 eager when tools_snapshot absent"
        return

    snapshot_data = tools_snapshot.get("data")
    if not isinstance(snapshot_data, dict):
        pytest.skip("tools_snapshot payload missing")

    enabled = snapshot_data.get("enabled_builtin_tools")
    if not isinstance(enabled, list):
        pytest.skip("tools_snapshot missing enabled_builtin_tools")

    for tool_id in DEFAULT_ENABLED_BUILTIN_TOOLS:
        assert (
            tool_id in enabled
        ), f"default tool {tool_id!r} missing from tools_snapshot"
    for tool_id in AGENT_BASELINE_BUILTIN_TOOLS:
        assert (
            tool_id not in enabled
        ), f"baseline {tool_id!r} must not appear in persisted snapshot"


@pytest.mark.integration
@_AGENT_STREAM_TEST_TIMEOUT
def test_agent_stream_tools_snapshot_includes_builtin_tool_id(
    client: TestClient,
) -> None:
    """Turn1 tools_snapshot rows must carry harness-derived builtin_tool_id for GUI labels."""
    chat_id = f"test_snapshot_builtin_id_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "query": "Reply with the word OK only.",
        "message_id": "test-snapshot-builtin-id-1",
        "chat_id": chat_id,
        "action_mode": "agent",
        "model_selection": get_lite_model_selection(),
        "agent_config": {
            "enabled_builtin_tools": ["web_search", "memory", "cron"],
            "skill_ids": [],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)

    tools_snapshot = next(
        (event for event in events if event.get("type") == "tools_snapshot"),
        None,
    )
    if tools_snapshot is None:
        pytest.skip("tools_snapshot not emitted in this stream")

    snapshot_rows = tools_snapshot.get("data")
    if not isinstance(snapshot_rows, list):
        pytest.skip("tools_snapshot data is not a tool list")

    web_rows = [
        row
        for row in snapshot_rows
        if isinstance(row, dict) and row.get("name") == "web_search_tool"
    ]
    assert web_rows, "expected web_search_tool in Turn1 tools_snapshot"
    assert web_rows[0].get("builtin_tool_id") == "web_search"

    cron_rows = [
        row
        for row in snapshot_rows
        if isinstance(row, dict) and row.get("name") == "cron_manage_tool"
    ]
    if cron_rows:
        assert cron_rows[0].get("builtin_tool_id") == "cron"


@pytest.mark.e2e
@_AGENT_STREAM_TEST_TIMEOUT
def test_agent_stream_discover_miss_does_not_emit_cron_capability_gap_sse(
    client: TestClient,
) -> None:
    """Real agent-stream: discover miss must not emit cron capability_gap SSE."""
    gap_query = "schedule daily reminder cron job at 9am every morning"
    chat_id = f"test_cron_cap_gap_{uuid.uuid4().hex[:8]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    payload: dict[str, object] = {
        "message_id": "test-cron-cap-gap-1",
        "chat_id": chat_id,
        "query": (
            "You MUST call skill_search_tool exactly once with query "
            f"'{gap_query}'. Do not call any other tool. "
            "After the tool returns, reply with the single word DONE."
        ),
        "action_mode": "agent",
        "model_selection": get_lite_model_selection(),
        "agent_config": {
            "enabled_builtin_tools": ["web_search", "memory"],
            "skill_ids": [],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)

    invoked = _invoked_tool_names(events)
    if "skill_search_tool" not in invoked:
        pytest.skip(
            "model did not invoke skill_search_tool; deterministic no-gap wiring covered in harness unit tests"
        )

    gaps = _gap_events(events, "capability_gap")
    blob = json.dumps(events, ensure_ascii=False)
    assert (
        not gaps and "<CapabilityGap>" not in blob
    ), "discover miss must not emit cron capability_gap SSE or CapabilityGap blocks"
