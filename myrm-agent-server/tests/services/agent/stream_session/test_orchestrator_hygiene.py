from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import JSONResponse

from app.services.agent.stream_session.orchestrator import run_agent_stream


@pytest.fixture
def mock_request():
    req = MagicMock()
    req.action_mode = "general"
    req.resume_value = None
    req.chat_id = "test_chat"
    req.sibling_group_id = None
    req.timestamp = None
    req.timezone = "UTC"
    req.engine_params = None
    req.steering_id = None
    req.mention_references = None
    req.ephemeral_subagents = None
    req.blueprint_id = None
    req.message_id = "test_msg"
    req.agent_id = "default"
    req.source = "web"
    req.session_id = "test"
    req.subagent_ids = None
    req.context_warnings = []
    req.extra_context = {}
    return req


@pytest.fixture
def mock_http_request():
    http_req = MagicMock()

    # Mock stream() to be an async generator
    async def _stream():
        yield b""

    http_req.stream = _stream
    return http_req


@pytest.mark.asyncio
async def test_run_agent_stream_hygiene_block(mock_request, mock_http_request, monkeypatch):
    """Test that gateway blocks massive text payloads."""
    # Create a payload of 360,001 characters
    massive_text = "A" * 360001
    mock_request.query = massive_text

    # Mock try_stream_reconnect and prevalidate_archive_restore_actions
    monkeypatch.setattr("app.services.agent.stream_session.orchestrator.try_stream_reconnect", AsyncMock(return_value=None))
    monkeypatch.setattr("app.services.agent.stream_session.orchestrator.check_stream_risk", AsyncMock(return_value=None))

    response = await run_agent_stream(mock_request, mock_http_request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    import json

    content = json.loads(response.body)
    assert "Request exceeds gateway token limits" in content["detail"]
