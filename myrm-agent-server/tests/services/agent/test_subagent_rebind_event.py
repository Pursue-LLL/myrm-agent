"""Tests for SUBAGENT_REBIND_REQUIRED when agent subagent_ids binding changes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.dto import AgentCreate, AgentUpdate
from app.database.migrations import ensure_raw_sql_schema
from app.database.models import Base
from app.services.agent.agent_service import AgentService
from app.services.event.app_event_bus import AppEventType

_PATCH_TARGET = "app.services.agent.agent_service.get_event_bus"


def _rebind_publish_calls(mock_bus: MagicMock) -> list[object]:
    return [
        call.args[0]
        for call in mock_bus.publish.call_args_list
        if call.args[0].event_type == AppEventType.SUBAGENT_REBIND_REQUIRED
    ]

@pytest_asyncio.fixture
async def agent_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_raw_sql_schema(engine)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import app.database.repositories.uow as uow_module

    original_factory = uow_module.get_session_factory
    uow_module.get_session_factory = lambda: session_factory

    yield session_factory

    uow_module.get_session_factory = original_factory
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_agent_subagent_ids_change_emits_rebind_event(agent_db) -> None:
    mock_bus = MagicMock()
    with (
        patch(_PATCH_TARGET, return_value=mock_bus),
        patch(
            "app.services.agent.external_cli_gate.assert_external_cli_tools_allowed",
            new=AsyncMock(),
        ),
    ):
        main_id = (
            await AgentService.create_agent(
                AgentCreate(name="Manager", description="delegation manager"),
            )
        ).id
        helper_id = (
            await AgentService.create_agent(
                AgentCreate(name="Helper", description="subagent helper"),
            )
        ).id
        outcome = await AgentService.update_agent(
            main_id,
            AgentUpdate(subagent_ids=[helper_id]),
        )

    assert outcome is not None
    rebind_events = _rebind_publish_calls(mock_bus)
    assert len(rebind_events) == 1
    event = rebind_events[0]
    assert event.event_type == AppEventType.SUBAGENT_REBIND_REQUIRED
    assert event.data["agent_id"] == main_id
    assert event.data["subagent_ids"] == [helper_id]


@pytest.mark.asyncio
async def test_update_agent_same_subagent_ids_does_not_emit_rebind_event(agent_db) -> None:
    mock_bus = MagicMock()
    with (
        patch(_PATCH_TARGET, return_value=mock_bus),
        patch(
            "app.services.agent.external_cli_gate.assert_external_cli_tools_allowed",
            new=AsyncMock(),
        ),
    ):
        helper_id = (
            await AgentService.create_agent(
                AgentCreate(name="Helper", description="subagent helper"),
            )
        ).id
        main_id = (
            await AgentService.create_agent(
                AgentCreate(
                    name="Manager",
                    description="delegation manager",
                    subagent_ids=[helper_id],
                ),
            )
        ).id
        outcome = await AgentService.update_agent(
            main_id,
            AgentUpdate(subagent_ids=[helper_id]),
        )

    assert outcome is not None
    assert _rebind_publish_calls(mock_bus) == []


@pytest.mark.asyncio
async def test_update_agent_non_subagent_field_does_not_emit_rebind_event(agent_db) -> None:
    mock_bus = MagicMock()
    with (
        patch(_PATCH_TARGET, return_value=mock_bus),
        patch(
            "app.services.agent.external_cli_gate.assert_external_cli_tools_allowed",
            new=AsyncMock(),
        ),
    ):
        main_id = (
            await AgentService.create_agent(
                AgentCreate(name="Manager", description="delegation manager"),
            )
        ).id
        outcome = await AgentService.update_agent(
            main_id,
            AgentUpdate(description="updated description only"),
        )

    assert outcome is not None
    assert _rebind_publish_calls(mock_bus) == []
