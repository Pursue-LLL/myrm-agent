"""A resumed run is screened on what the user typed into the answer: the rejection reason and guidance of an approval.

An option pick, an edited tool argument or a plan the user adjusted is built from text the agent wrote, so it is not
screened: a rule would hold a click on something the user never typed.
"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import StreamingResponse

from app.services.agent.params.models import TurnCapabilityTelemetryRequest
from app.services.agent.stream_session import run_agent_stream
from app.services.agent.stream_session.risk_gate import resume_typed_texts
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


def _hold_api_keys(monkeypatch: pytest.MonkeyPatch) -> tuple[AsyncMock, AsyncMock]:
    """Wire the gate to a rule set that holds API keys; returns the context guard and the hit recorder to watch."""
    from app.services.agent.context_guard_service import ContextGuardService

    guard = AsyncMock()
    monkeypatch.setattr(ContextGuardService, "guard_inbound_prompt", guard)
    monkeypatch.setattr(f"{_ORCHESTRATOR}.try_stream_reconnect", AsyncMock(return_value=None))
    service, record_hits = _service_holding_api_keys()
    monkeypatch.setattr("app.services.risk.detection.get_detection_service", lambda: service)
    monkeypatch.setattr("app.platform_utils.get_session_factory", lambda: _FakeSession)
    return guard, record_hits


async def _body_text(response: StreamingResponse) -> str:
    return "".join([chunk if isinstance(chunk, str) else bytes(chunk).decode() async for chunk in response.body_iterator])


@pytest.fixture
def http_request() -> MagicMock:
    async def _stream() -> AsyncIterator[bytes]:
        yield b""

    http = MagicMock()
    http.stream = _stream
    return http


def _resume_request(resume_value: dict[str, object]) -> MagicMock:
    request = MagicMock()
    request.action_mode = "general"
    request.resume_value = resume_value
    request.chat_id = "chat-resume"
    request.message_id = "msg-resume"
    request.query = ""
    request.regenerate_instruction = None
    return request


@pytest.mark.parametrize(
    "resume_value",
    [
        pytest.param({"decisions": [{"type": "reject", "feedback": f"use {SECRET}"}]}, id="rejection-reason"),
        pytest.param({"decisions": [{"type": "approve", "guidance": f"use {SECRET}"}]}, id="guidance"),
        pytest.param({"decision": "reject", "feedback": f"use {SECRET}"}, id="semantic-dom-decision"),
    ],
)
async def test_a_secret_typed_into_an_approval_answer_is_held_before_the_run_resumes(
    resume_value: dict[str, object], http_request: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    guard, record_hits = _hold_api_keys(monkeypatch)

    response = await run_agent_stream(_resume_request(resume_value), http_request)

    assert isinstance(response, StreamingResponse)
    body = await _body_text(response)
    assert "risk_blocked" in body
    assert SECRET not in body
    guard.assert_not_awaited()
    record_hits.assert_awaited_once()


async def test_a_held_answer_ends_the_send_as_held_not_as_a_server_error(
    http_request: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hold_api_keys(monkeypatch)
    failed = AsyncMock()
    monkeypatch.setattr(f"{_ORCHESTRATOR}.record_turn_capability_send_failed", failed)
    request = _resume_request({"decisions": [{"type": "reject", "feedback": f"use {SECRET}"}]})
    request.turn_capability_telemetry = TurnCapabilityTelemetryRequest(
        source="direct", effective_skill_count=1, effective_mcp_count=0
    )

    await run_agent_stream(request, http_request)

    failed.assert_awaited_once_with(request, "risk_held")


async def test_every_typed_text_of_a_batch_is_screened_and_nothing_else(
    http_request: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = StreamingResponse(iter(["held"]))
    gate = AsyncMock(side_effect=[None, None, held])
    monkeypatch.setattr(f"{_ORCHESTRATOR}.check_stream_risk", gate)
    monkeypatch.setattr(f"{_ORCHESTRATOR}.try_stream_reconnect", AsyncMock(return_value=None))
    resume_value: dict[str, object] = {
        "decisions": [
            {"type": "reject", "feedback": "first reason", "args": {"command": f"echo {SECRET}"}},
            {"type": "approve", "guidance": "second guidance"},
            {"type": "reject", "feedback": "third reason"},
        ]
    }

    response = await run_agent_stream(_resume_request(resume_value), http_request)

    assert response is held
    assert [call.args[0] for call in gate.await_args_list] == ["first reason", "second guidance", "third reason"]


@pytest.mark.parametrize(
    ("resume_value", "expected"),
    [
        pytest.param(
            {"decisions": [{"type": "reject", "feedback": "no", "guidance": "use staging"}]}, ["no", "use staging"], id="both"
        ),
        pytest.param({"decision": "reject", "feedback": "no"}, ["no"], id="semantic-dom"),
        pytest.param({"decisions": [{"type": "approve", "feedback": None, "guidance": "  "}]}, [], id="empty-or-absent"),
        pytest.param({"decisions": [{"type": "edit", "args": {"command": f"echo {SECRET}"}}]}, [], id="edited-arguments"),
        pytest.param({"q1": ["option a", "typed"], "feedback": ["option b"]}, [], id="clarification-answer"),
        pytest.param({"action": "edit", "modified_plan": f"step {SECRET}"}, [], id="adjusted-plan"),
        pytest.param({"decisions": "malformed", "decision": "reject", "feedback": 7}, [], id="malformed"),
    ],
)
def test_only_the_text_typed_into_an_approval_decision_is_screened(resume_value: dict[str, object], expected: list[str]) -> None:
    assert resume_typed_texts(resume_value) == expected
