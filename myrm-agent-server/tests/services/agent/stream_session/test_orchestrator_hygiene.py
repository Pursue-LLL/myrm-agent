from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import JSONResponse

from app.services.agent.stream_session import run_agent_stream


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


def test_run_agent_stream_facade_lazy_import():
    """The package facade must not eagerly load the orchestrator module.

    Importing the facade is the hot path during service startup; the
    orchestrator drags in a heavy dependency chain (qdrant etc.), so it is
    deliberately lazy-imported on first call. This guards that contract so a
    future refactor cannot silently regress startup time.

    The check runs in a fresh subprocess interpreter: reloading the package
    in-process would re-trigger module-level prometheus Counter registration.
    """
    import subprocess
    import sys
    import textwrap

    probe = textwrap.dedent(
        """
        import sys
        import app.services.agent.stream_session as facade
        orchestrator = "app.services.agent.stream_session.orchestrator"
        assert orchestrator not in sys.modules, "facade eagerly loaded orchestrator"
        assert facade.run_agent_stream.__module__ == "app.services.agent.stream_session"
        print("LAZY_OK")
        """
    )
    server_root = Path(__file__).resolve().parents[4]
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=server_root,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "LAZY_OK" in result.stdout


def test_run_agent_stream_facade_signature_matches_orchestrator():
    """The facade must expose the exact signature of the orchestrator impl.

    This is the regression guard for the precise-typing fix: a drift between
    facade and implementation would let a wrong-typed call slip through.
    """
    import inspect

    from app.services.agent.stream_session.orchestrator import (
        run_agent_stream as orchestrator_run,
    )

    facade_sig = inspect.signature(run_agent_stream)
    orchestrator_sig = inspect.signature(orchestrator_run)
    assert facade_sig == orchestrator_sig


@pytest.mark.asyncio
async def test_run_agent_stream_hygiene_block(
    mock_request, mock_http_request, monkeypatch
):
    """Test that gateway blocks massive text payloads."""
    # Create a payload of 360,001 characters
    massive_text = "A" * 360001
    mock_request.query = massive_text

    # Mock try_stream_reconnect and prevalidate_archive_restore_actions
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.try_stream_reconnect",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.check_stream_risk",
        AsyncMock(return_value=None),
    )

    response = await run_agent_stream(mock_request, mock_http_request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    import json

    content = json.loads(response.body)
    assert "Request exceeds gateway token limits" in content["detail"]
