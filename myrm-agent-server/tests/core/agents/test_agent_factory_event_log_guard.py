"""Guard test: create_general_agent must not create an event-log backend for unsafe chat_ids."""

from unittest.mock import MagicMock, patch

import pytest

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.core.types.business import ModelConfig


def _minimal_params(chat_id: str | None) -> GeneralAgentParams:
    return GeneralAgentParams(
        model_cfg=ModelConfig(model="gpt-4o", api_key="test-key"),
        query="test query",
        chat_id=chat_id,
        enable_browser=False,
        prompt_mode="full",
    )


@pytest.mark.parametrize(
    ("chat_id", "backend_created"),
    [
        ("kanban:abcd1234ef56", True),  # 合法：创建 backend
        (None, False),  # 无 chat_id：不创建
        ("../../etc/passwd", False),  # 恶意：跳过写入
    ],
)
def test_create_general_agent_guards_event_log_backend(chat_id: str | None, backend_created: bool):
    """Unsafe chat_ids must never reach FileEventLogBackend (path escape guard)."""
    with (
        patch(
            "myrm_agent_harness.agent.event_log.backends.file_backend.FileEventLogBackend",
            return_value=MagicMock(name="backend"),
        ) as backend_cls,
        patch("app.ai_agents.general_agent.GeneralAgent", return_value=MagicMock()),
    ):
        params = _minimal_params(chat_id)
        params.event_log_dir = "/tmp/event-logs"

        AgentFactory.create_general_agent(params)

    assert backend_cls.called is backend_created
