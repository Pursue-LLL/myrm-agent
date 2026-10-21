"""The single entry that holds a user's typed text: detection, hit record and failure behaviour on a real SQLite engine."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import RiskHit
from app.services.risk.detection import POSITION_SUMMARY_PREFIX
from app.services.risk.ingress import screen_user_text

from .conftest import EngineBuilder

_SECRET_LINE = "password: Zk9#mango42"


async def _stored_hits(session_factory: async_sessionmaker[AsyncSession]) -> list[RiskHit]:
    async with session_factory() as db:
        return list((await db.execute(select(RiskHit))).scalars())


async def test_secret_is_held_and_recorded_by_position_only(
    build_engine: EngineBuilder, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    service = await build_engine()
    with (
        patch("app.services.risk.detection.get_detection_service", return_value=service),
        patch("app.platform_utils.get_session_factory", return_value=session_factory),
    ):
        result = await screen_user_text(f"here it is\n{_SECRET_LINE}", session_id="chat-1")

    assert result is not None and result.blocked
    (hit,) = await _stored_hits(session_factory)
    assert hit.session_id == "chat-1"
    assert hit.match_summary.startswith(POSITION_SUMMARY_PREFIX)
    assert "Zk9" not in hit.match_summary


async def test_held_text_is_not_recorded_when_the_caller_leaves_that_to_a_later_path(
    build_engine: EngineBuilder, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    service = await build_engine()
    with (
        patch("app.services.risk.detection.get_detection_service", return_value=service),
        patch("app.platform_utils.get_session_factory", return_value=session_factory),
    ):
        result = await screen_user_text(_SECRET_LINE, session_id=None, record=False)

    assert result is not None and result.blocked
    assert await _stored_hits(session_factory) == []


@pytest.mark.parametrize("text", [None, "", "how do I rotate an API key safely?"])
async def test_text_without_a_secret_passes_and_leaves_no_record(
    build_engine: EngineBuilder, session_factory: async_sessionmaker[AsyncSession], text: str | None
) -> None:
    service = await build_engine()
    with (
        patch("app.services.risk.detection.get_detection_service", return_value=service),
        patch("app.platform_utils.get_session_factory", return_value=session_factory),
    ):
        assert await screen_user_text(text, session_id="chat-1") is None

    assert await _stored_hits(session_factory) == []


async def test_no_loaded_rules_passes_everything(build_engine: EngineBuilder) -> None:
    service = await build_engine(seed_builtins=False)
    with patch("app.services.risk.detection.get_detection_service", return_value=service):
        assert await screen_user_text(_SECRET_LINE, session_id="chat-1") is None


async def test_failure_to_record_still_holds_the_text(build_engine: EngineBuilder) -> None:
    service = await build_engine()
    with (
        patch("app.services.risk.detection.get_detection_service", return_value=service),
        patch("app.platform_utils.get_session_factory", side_effect=RuntimeError("database unavailable")),
    ):
        result = await screen_user_text(_SECRET_LINE, session_id="chat-1")

    assert result is not None and result.blocked
