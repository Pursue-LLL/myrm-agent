"""The web risk gate reads the prompt as typed: a long paste is screened before the context guard shortens it to a stub."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import StreamingResponse

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


def _service_holding_api_keys() -> RiskDetectionService:
    service = build_service_with_rules([API_KEY_RULE])
    service.record_hits = AsyncMock()  # type: ignore[method-assign]
    return service


@pytest.fixture
def long_paste_request() -> MagicMock:
    request = MagicMock()
    request.action_mode = "general"
    request.resume_value = None
    request.chat_id = "chat-risk"
    request.message_id = "msg-risk"
    request.query = "ordinary log line\n" * 1500 + f"Authorization key {SECRET}\n"
    return request


@pytest.fixture
def http_request() -> MagicMock:
    async def _stream():
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
    service = _service_holding_api_keys()
    monkeypatch.setattr("app.services.risk.detection.get_detection_service", lambda: service)
    monkeypatch.setattr("app.platform_utils.get_session_factory", lambda: _FakeSession)

    response = await run_agent_stream(long_paste_request, http_request)

    assert isinstance(response, StreamingResponse)
    body = "".join([chunk async for chunk in response.body_iterator])
    assert "risk_blocked" in body
    assert SECRET not in body
    spill.assert_not_awaited()
    service.record_hits.assert_awaited_once()
