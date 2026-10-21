"""Guard test: create_general_agent must not create an event-log backend for unsafe chat_ids or incognito chats."""

from unittest.mock import MagicMock, patch

import pytest

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.core.types.business import ModelConfig


def _minimal_params(chat_id: str | None, *, incognito: bool = False) -> GeneralAgentParams:
    return GeneralAgentParams(
        model_cfg=ModelConfig(model="gpt-4o", api_key="test-key"),
        query="test query",
        chat_id=chat_id,
        enable_browser=False,
        prompt_mode="full",
        incognito_mode=incognito,
    )


@pytest.mark.parametrize(
    ("chat_id", "incognito", "backend_created"),
    [
        ("kanban:abcd1234ef56", False, True),  # 合法：创建 backend
        ("kanban:abcd1234ef56", True, False),  # 隐身：事件日志含完整提示词与工具结果，不得落盘
        (None, False, False),  # 无 chat_id：不创建
        ("../../etc/passwd", False, False),  # 恶意：跳过写入
    ],
)
def test_create_general_agent_guards_event_log_backend(chat_id: str | None, incognito: bool, backend_created: bool):
    """Unsafe chat_ids must never reach FileEventLogBackend (path escape guard); incognito chats keep no event log."""
    with (
        patch(
            "myrm_agent_harness.agent.event_log.backends.file_backend.FileEventLogBackend",
            return_value=MagicMock(name="backend"),
        ) as backend_cls,
        patch("app.ai_agents.general_agent.GeneralAgent", return_value=MagicMock()) as agent_cls,
    ):
        params = _minimal_params(chat_id, incognito=incognito)
        params.event_log_dir = "/tmp/event-logs"

        AgentFactory.create_general_agent(params)

    assert backend_cls.called is backend_created
    assert (agent_cls.call_args.kwargs["event_log_backend"] is not None) is backend_created
