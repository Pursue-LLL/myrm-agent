import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.ai_agents.general_agent.compression_intent import build_compression_intent


def test_build_compression_intent_extracts_focus_from_query_and_recent_human_turns() -> None:
    intent = build_compression_intent(
        query="修复 myrm-agent-harness/src/myrm_agent_harness/agent/context_management/pipeline/engine.py 里的 builder，并检查 app.services.agent",
        chat_history=[
            HumanMessage(content="之前一直在看 app/ai_agents/general_agent/agent.py"),
            AIMessage(content="ack"),
        ],
    )

    assert intent == {
        "focus_files": [
            "myrm-agent-harness/src/myrm_agent_harness/agent/context_management/pipeline/engine.py",
            "app/ai_agents/general_agent/agent.py",
        ],
        "focus_modules": ["app.services.agent"],
        "failed_tool_call_ids": [],
        "user_goal_hint": "修复 myrm-agent-harness/src/myrm_agent_harness/agent/context_management/pipeline/engine.py 里的 builder，并检查 app.services.agent",
    }


def test_build_compression_intent_ignores_non_human_history_noise() -> None:
    intent = build_compression_intent(
        query="继续修 auth",
        chat_history=[
            ToolMessage(
                content="Look at /tmp/noise.py and internal.module",
                tool_call_id="call_1",
                name="bash",
            ),
            AIMessage(content="assistant text mentions app.fake.module"),
            HumanMessage(content="重点看 app/services/agent/agent_service.py 和 app.services.agent"),
        ],
    )

    assert intent == {
        "focus_files": ["app/services/agent/agent_service.py"],
        "focus_modules": ["app.services.agent"],
        "failed_tool_call_ids": [],
        "user_goal_hint": "继续修 auth",
    }


def test_build_compression_intent_supports_multimodal_text_query() -> None:
    intent = build_compression_intent(
        query=[
            {"type": "text", "text": "修复 app/core/channel_bridge/agent_executor.py，并关注 app.core.channel_bridge"},
            {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
        ],
        chat_history=[],
    )

    assert intent == {
        "focus_files": ["app/core/channel_bridge/agent_executor.py"],
        "focus_modules": ["app.core.channel_bridge"],
        "failed_tool_call_ids": [],
        "user_goal_hint": "修复 app/core/channel_bridge/agent_executor.py，并关注 app.core.channel_bridge",
    }


def test_build_compression_intent_collects_failed_tool_call_ids_from_history() -> None:
    intent = build_compression_intent(
        query="继续",
        chat_history=[
            HumanMessage(content="继续排查工具失败"),
            ToolMessage(content="bash execution failed: exit code 1", tool_call_id="call_failed_1", name="bash"),
            ToolMessage(content="completed successfully", tool_call_id="call_ok", name="bash"),
            ToolMessage(content="Permission denied", tool_call_id="call_failed_2", name="bash", status="error"),
        ],
    )

    assert intent == {
        "focus_files": [],
        "focus_modules": [],
        "failed_tool_call_ids": ["call_failed_1", "call_failed_2"],
        "user_goal_hint": "继续排查工具失败",
    }


def test_build_compression_intent_returns_none_for_generic_signal_only() -> None:
    intent = build_compression_intent(
        query="继续",
        chat_history=[],
    )

    assert intent is None


def test_build_compression_intent_includes_pinned_files_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_read_pinned_files(chat_id: str) -> list[str]:
        assert chat_id == "chat-with-pins"
        return ["src/context/retention.py"]

    monkeypatch.setattr(
        "myrm_agent_harness.runtime.context.session.session_context_pins.read_pinned_files",
        _fake_read_pinned_files,
    )

    intent = build_compression_intent(
        query="继续",
        chat_history=[],
        chat_id="chat-with-pins",
    )

    assert intent == {
        "focus_files": [],
        "focus_modules": [],
        "failed_tool_call_ids": [],
        "user_goal_hint": "",
        "pinned_files": ["src/context/retention.py"],
    }


def test_build_compression_intent_swallows_pinned_file_load_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(_chat_id: str) -> list[str]:
        raise RuntimeError("pin store unavailable")

    monkeypatch.setattr(
        "myrm_agent_harness.runtime.context.session.session_context_pins.read_pinned_files",
        _raise,
    )

    intent = build_compression_intent(
        query="修复 app/services/agent/agent_service.py",
        chat_history=[],
        chat_id="chat-pin-error",
    )

    assert intent is not None
    assert "pinned_files" not in intent
    assert intent["focus_files"] == ["app/services/agent/agent_service.py"]


def test_build_compression_intent_ignores_non_query_shapes_and_url_paths() -> None:
    intent = build_compression_intent(
        query=123,
        chat_history=[
            HumanMessage(
                content=[
                    {"type": "text", "text": "prior work on app/core/agent.py"},
                    "app/core/agent.py",
                ],
            ),
        ],
    )

    assert intent == {
        "focus_files": ["app/core/agent.py"],
        "focus_modules": [],
        "failed_tool_call_ids": [],
        "user_goal_hint": "prior work on app/core/agent.py app/core/agent.py",
    }


def test_build_compression_intent_collects_error_prefixed_tool_failures() -> None:
    intent = build_compression_intent(
        query="继续",
        chat_history=[
            HumanMessage(content="排查失败"),
            ToolMessage(content="[ERROR] tool exploded", tool_call_id="call_err", name="bash"),
            ToolMessage(content="[ERROR] duplicate", tool_call_id="call_err", name="bash"),
            ToolMessage(content="still running", tool_call_id="call_ok", name="bash"),
        ],
    )

    assert intent == {
        "focus_files": [],
        "focus_modules": [],
        "failed_tool_call_ids": ["call_err"],
        "user_goal_hint": "排查失败",
    }


def test_build_compression_intent_handles_command_object() -> None:
    """Test that _extract_query_text handles langgraph Command objects."""

    class FakeCommand:
        """Simulates langgraph.types.Command with a resume attribute."""

        def __init__(self, resume: str) -> None:
            self.resume = resume

    intent = build_compression_intent(
        query=FakeCommand(resume="检查 app/services/agent/agent_service.py 的 bug"),
        chat_history=[],
    )

    assert intent is not None
    assert "app/services/agent/agent_service.py" in intent["focus_files"]


def test_build_compression_intent_handles_command_with_non_string_resume() -> None:
    """When Command.resume is a dict (e.g., tool approval), should not crash."""

    class FakeCommand:
        def __init__(self, resume: object) -> None:
            self.resume = resume

    intent = build_compression_intent(
        query=FakeCommand(resume={"tool_call_id": "call_1", "approved": True}),
        chat_history=[HumanMessage(content="查看 app/core/agent.py")],
    )

    assert intent is not None
    assert "app/core/agent.py" in intent["focus_files"]
