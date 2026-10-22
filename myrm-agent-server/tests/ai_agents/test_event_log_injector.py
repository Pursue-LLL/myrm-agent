"""测试统一事件日志配置注入器、会话标识解析器与门控告警."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.ai_agents.agent_params import GeneralAgentParams
from app.ai_agents.agents import AgentFactory
from app.ai_agents.event_log_injector import (
    get_default_event_log_config,
    inject_event_log_config,
    resolve_cron_event_log_session_id,
    resolve_voice_realtime_session_id,
    sanitize_channel_event_log_session_id,
)
from app.core.types import ModelConfig
from app.core.utils.session_id import is_safe_session_id


def test_cron_session_id_resolution_and_safety() -> None:
    """测试定时任务独立会话标识生成与安全白名单."""
    target_date = date(2026, 10, 13)
    # 正常 ID
    sid = resolve_cron_event_log_session_id("nightly_backup", run_date=target_date)
    assert sid == "cron:nightly_backup:2026-10-13"
    assert is_safe_session_id(sid)

    # 包含空格与特殊字符的 ID
    sid_dirty = resolve_cron_event_log_session_id("job #1 / cleanup", run_date=target_date)
    assert sid_dirty == "cron:job__1___cleanup:2026-10-13"
    assert is_safe_session_id(sid_dirty)


def test_voice_realtime_session_id_resolution() -> None:
    """测试实时语音入口按日分片防无限增长."""
    target_date = date(2026, 10, 13)

    # 空或 None
    sid_none = resolve_voice_realtime_session_id(None, run_date=target_date)
    assert sid_none == "voice:realtime:2026-10-13"
    assert is_safe_session_id(sid_none)

    # 硬编码的旧固定字面量被替换为分片
    sid_literal = resolve_voice_realtime_session_id("realtime-tool", run_date=target_date)
    assert sid_literal == "voice:realtime:2026-10-13"
    assert is_safe_session_id(sid_literal)

    # 外部传入合法安全 chat_id 保留
    sid_custom = resolve_voice_realtime_session_id("voice-call-abc123", run_date=target_date)
    assert sid_custom == "voice-call-abc123"
    assert is_safe_session_id(sid_custom)


def test_channel_session_id_sanitization() -> None:
    """测试渠道与外部标识安全过滤."""
    # 正常安全标识
    assert sanitize_channel_event_log_session_id("tg:user_456") == "tg:user_456"

    # 恶意穿越或非法字符
    cleaned = sanitize_channel_event_log_session_id("../../etc/passwd", default_prefix="ch")
    assert ".." not in cleaned
    assert "/" not in cleaned
    assert is_safe_session_id(cleaned)

    # 空字符串生成回退标识
    fallback = sanitize_channel_event_log_session_id("", default_prefix="my_chan")
    assert fallback.startswith("my_chan:unnamed:")
    assert is_safe_session_id(fallback)


def test_inject_event_log_config() -> None:
    """测试统一注入配置到 GeneralAgentParams."""
    params = GeneralAgentParams(
        query="hello",
        chat_id="chat-1",
        model_cfg=ModelConfig(model="mock-model", apiKey="sk-mock"),
    )
    assert params.event_log_dir is None
    assert params.event_log_session_id is None

    with patch(
        "app.ai_agents.event_log_injector.get_default_event_log_config",
        return_value=("/tmp/myrm_event_logs", 50000),
    ):
        inject_event_log_config(params, session_id_override="cron:job1:2026-10-13")

    assert params.event_log_dir == "/tmp/myrm_event_logs"
    assert params.event_log_max_jsonl_line_bytes == 50000
    assert params.event_log_session_id == "cron:job1:2026-10-13"


def test_agents_gate_observability_and_session_id_priority(tmp_path: pytest.TempPathFactory) -> None:
    """测试 AgentFactory.create_general_agent 门控对 event_log_session_id 的优先级与告警日志."""
    log_dir = str(tmp_path)

    # 1. 优先使用 event_log_session_id 而非 chat_id
    params = GeneralAgentParams(
        query="hi",
        chat_id="web-chat-user",
        model_cfg=ModelConfig(model="mock-model", apiKey="sk-mock"),
        event_log_session_id="cron:job_x:2026-10-13",
        event_log_dir=log_dir,
    )

    with patch("myrm_agent_harness.agent.event_log.backends.file_backend.FileEventLogBackend") as mock_backend:
        with patch("app.ai_agents.general_agent.GeneralAgent") as mock_agent_cls:
            mock_agent_instance = MagicMock()
            mock_agent_cls.return_value = mock_agent_instance
            AgentFactory.create_general_agent(params)

            # 验证 mock_backend 使用了 event_log_session_id
            mock_backend.assert_called_once()
            _, kwargs = mock_backend.call_args
            assert kwargs["session_id"] == "cron:job_x:2026-10-13"

    # 2. 不安全的 session_id 触发 warning 且不创建后端
    unsafe_params = GeneralAgentParams(
        query="hi",
        chat_id="../../unsafe_dir",
        model_cfg=ModelConfig(model="mock-model", apiKey="sk-mock"),
        event_log_dir=log_dir,
    )
    with patch("app.ai_agents.agents.logger.warning") as mock_warn:
        with patch("myrm_agent_harness.agent.event_log.backends.file_backend.FileEventLogBackend") as mock_backend:
            with patch("app.ai_agents.general_agent.GeneralAgent"):
                AgentFactory.create_general_agent(unsafe_params)
                mock_backend.assert_not_called()
                mock_warn.assert_called_once()
                assert "rejected by whitelist" in mock_warn.call_args[0][0]
