"""The web risk gate reads what was typed: a long paste is screened before the context guard shortens it to a stub, and the
regeneration guidance is screened on its own, without joining the prompt the guard and the size check read."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.agent.stream_session import run_agent_stream
from app.services.risk.detection import RiskDetectionService
from tests.support.risk_gate import API_KEY_RULE, SECRET, build_service_with_rules

_ORCHESTRATOR = "app.services.agent.stream_session.orchestrator"


class _FakeSession:
    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    async def commit(self) -> None:
        return None


def _service_holding_api_keys() -> tuple[RiskDetectionService, AsyncMock]:
    service = build_service_with_rules([API_KEY_RULE])
    record_hits = AsyncMock()
    service.record_hits = record_hits  # type: ignore[method-assign]
    return service, record_hits


async def _body_text(response: StreamingResponse) -> str:
    return "".join([chunk if isinstance(chunk, str) else bytes(chunk).decode() async for chunk in response.body_iterator])


@pytest.fixture
def long_paste_request() -> MagicMock:
    request = MagicMock()
    request.action_mode = "general"
    request.resume_value = None
    request.chat_id = "chat-risk"
    request.message_id = "msg-risk"
    request.query = "ordinary log line\n" * 1500 + f"Authorization key {SECRET}\n"
    request.regenerate_instruction = None
    return request


@pytest.fixture
def regeneration_request() -> MagicMock:
    request = MagicMock()
    request.action_mode = "general"
    request.resume_value = None
    request.chat_id = "chat-regen"
    request.message_id = "msg-regen"
    request.query = "summarise the report"
    request.regenerate_instruction = f"use {SECRET}"
    return request


@pytest.fixture
def http_request() -> MagicMock:
    async def _stream() -> AsyncIterator[bytes]:
        yield b""

    http = MagicMock()
    http.stream = _stream
    return http


async def test_secret_in_a_paste_the_guard_would_spill_is_held_first(
    long_paste_request: MagicMock, http_request: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.agent.context_guard_service import ContextGuardService

    assert len(long_paste_request.query) > 16_000
    spill = AsyncMock()
    monkeypatch.setattr(ContextGuardService, "guard_inbound_prompt", spill)
    monkeypatch.setattr(f"{_ORCHESTRATOR}.try_stream_reconnect", AsyncMock(return_value=None))
    service, record_hits = _service_holding_api_keys()
    monkeypatch.setattr("app.services.risk.detection.get_detection_service", lambda: service)
    monkeypatch.setattr("app.platform_utils.get_session_factory", lambda: _FakeSession)

    response = await run_agent_stream(long_paste_request, http_request)

    assert isinstance(response, StreamingResponse)
    body = await _body_text(response)
    assert "risk_blocked" in body
    assert SECRET not in body
    spill.assert_not_awaited()
    record_hits.assert_awaited_once()


async def test_secret_in_the_regeneration_guidance_is_held(
    regeneration_request: MagicMock, http_request: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.agent.context_guard_service import ContextGuardService

    spill = AsyncMock()
    monkeypatch.setattr(ContextGuardService, "guard_inbound_prompt", spill)
    monkeypatch.setattr(f"{_ORCHESTRATOR}.try_stream_reconnect", AsyncMock(return_value=None))
    service, record_hits = _service_holding_api_keys()
    monkeypatch.setattr("app.services.risk.detection.get_detection_service", lambda: service)
    monkeypatch.setattr("app.platform_utils.get_session_factory", lambda: _FakeSession)

    response = await run_agent_stream(regeneration_request, http_request)

    assert isinstance(response, StreamingResponse)
    body = await _body_text(response)
    assert "risk_blocked" in body
    assert SECRET not in body
    spill.assert_not_awaited()
    record_hits.assert_awaited_once()


async def test_the_guard_and_size_check_read_the_prompt_without_the_regeneration_guidance(
    regeneration_request: MagicMock, http_request: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A spilled prompt is written back into ``request.query``, so the guidance must not be part of what the guard reads."""
    from app.services.agent.context_guard_service import ContextGuardService

    regeneration_request.query = "A" * 360_001
    regeneration_request.regenerate_instruction = "be more concise"
    gate = AsyncMock(return_value=None)
    guard = AsyncMock(return_value=SimpleNamespace(spilled=False))
    monkeypatch.setattr(f"{_ORCHESTRATOR}.check_stream_risk", gate)
    monkeypatch.setattr(f"{_ORCHESTRATOR}.try_stream_reconnect", AsyncMock(return_value=None))
    monkeypatch.setattr(ContextGuardService, "guard_inbound_prompt", guard)

    response = await run_agent_stream(regeneration_request, http_request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    assert [call.args[0] for call in gate.await_args_list] == [regeneration_request.query, "be more concise"]
    guard.assert_awaited_once_with(chat_id="chat-regen", raw_prompt=regeneration_request.query, role="user")
