"""@input: tests.support.scripted_openai_endpoint (scripted model), tests.api.agent.conftest (mock user configs and test database), app.database.factory (production engine policy)
@output: TurnResult, scripted_model_environment, connection_per_session, stream_agent_turn, wait_for
@pos: [T] Points the app's model credentials at a ScriptedOpenAIEndpoint and drives agent-stream turns, so an agent API test runs a real agent against a deterministic model.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine

from app import platform_utils
from app.database.factory import register_sqlite_transaction_events, set_sqlite_pragma
from tests.api.agent.conftest import _build_mock_user_configs
from tests.api.agent.utils import get_lite_model_selection, get_model_selection, get_search_service_config
from tests.support import test_secrets
from tests.support.scripted_openai_endpoint import ScriptedOpenAIEndpoint


@dataclass(frozen=True)
class TurnResult:
    """One agent-stream request: the HTTP status and, for an accepted request, the events it streamed."""

    status: int
    events: list[dict[str, object]]

    def of_type(self, event_type: str) -> list[dict[str, object]]:
        return [event for event in self.events if event.get("type") == event_type]

    @property
    def text(self) -> str:
        return "".join(str(event.get("data", "")) for event in self.of_type("message"))


@contextmanager
def scripted_model_environment(
    endpoint: ScriptedOpenAIEndpoint,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_load_user_configs: AsyncMock,
) -> Iterator[None]:
    """Point every model credential the app tests read at the scripted endpoint."""
    env = {
        "BASIC_API_KEY": "scripted-key",
        "BASIC_BASE_URL": endpoint.base_url,
        "BASIC_MODEL": "openai/scripted-model",
        "LITE_API_KEY": "scripted-key",
        "LITE_BASE_URL": endpoint.base_url,
        "LITE_MODEL": "openai/scripted-model",
        "EMBEDDING_API_KEY": "scripted-key",
        "EMBEDDING_BASE_URL": endpoint.base_url,
        "OPENAI_API_KEY": "scripted-key",
        "OPENAI_BASE_URL": endpoint.base_url,
        "OPENAI_API_BASE": endpoint.base_url,
        "SEARCH_SERVICE": "tavily",
        "TAVILY_API_KEY": "scripted-key",
    }
    (tmp_path / ".env.test").write_text("".join(f"{key}={value}\n" for key, value in env.items()))
    monkeypatch.setattr(test_secrets, "_SERVER_ROOT", tmp_path)
    test_secrets.clear_test_secrets_cache()
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    mock_load_user_configs.return_value = _build_mock_user_configs()
    # Whoever asks, the configured search provider is not probed live: a scripted test must not leave the machine.
    monkeypatch.setattr("app.services.integrations.search_verify.verify_search_config_cached", AsyncMock(return_value=False))
    try:
        yield
    finally:
        test_secrets.clear_test_secrets_cache()


@asynccontextmanager
async def connection_per_session(database_file: Path) -> AsyncIterator[None]:
    """Serve the sessions of the shared test database with a connection each, the way production does.

    The shared fixture hands every session one and the same connection, so a rollback or commit of one session lands
    in the middle of another's transaction. Two tasks that write at the same moment (a timer-resumed run and the
    teardown of the turn that armed it) then lose writes silently, which a production pool cannot do.
    """
    factory = platform_utils.get_session_factory()
    shared_engine = factory.kw["bind"]
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_file}", connect_args={"check_same_thread": False}, pool_size=4, max_overflow=4
    )
    event.listen(engine.sync_engine, "connect", set_sqlite_pragma)
    register_sqlite_transaction_events(engine)
    factory.configure(bind=engine)
    try:
        yield
    finally:
        factory.configure(bind=shared_engine)
        await engine.dispose()


def stream_agent_turn(
    client: TestClient,
    chat_id: str,
    *,
    query: str = "",
    resume_value: dict[str, object] | None = None,
    agent_config: dict[str, object] | None = None,
) -> TurnResult:
    """POST one agent-stream turn (a new message, or the answer to a paused one) and collect what it streams."""
    body: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "chatId": chat_id,
        "query": query,
        "action_mode": "agent",
        "modelSelection": get_model_selection(),
        "liteModelSelection": get_lite_model_selection(),
        "searchServiceCfg": get_search_service_config(),
        "enable_memory_auto_extraction": False,
    }
    if resume_value is not None:
        body["resumeValue"] = resume_value
    if agent_config is not None:
        body["agentConfig"] = agent_config
    events: list[dict[str, object]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=body, headers={"X-Chat-ID": chat_id}) as response:
        if response.status_code == 200:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    payload = json.loads(line[len("data: ") :])
                    if isinstance(payload, dict):
                        events.append(payload)
        return TurnResult(response.status_code, events)


def wait_for[T](read: Callable[[], T], done: Callable[[T], bool], timeout: float = 15.0) -> T:
    """Poll ``read`` until ``done`` accepts its value or ``timeout`` seconds pass; returns the last value read."""
    deadline = time.monotonic() + timeout
    value = read()
    while not done(value) and time.monotonic() < deadline:
        time.sleep(0.2)
        value = read()
    return value
