from langchain_core.messages import HumanMessage, ToolMessage
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.ai_agents.general_agent import GeneralAgent
from app.core.types import ModelConfig


def _build_agent(**overrides: object) -> GeneralAgent:
    params = {
        "model_cfg": ModelConfig(provider="openai", model="gpt-4o-mini", api_key="test"),
        "mcp_config": None,
        "search_service_cfg": SearchServiceConfig(search_service="searxng"),
        "chat_id": "chat-root",
        "channel_name": "web_chat",
        "agent_id": "planner",
    }
    params.update(overrides)
    return GeneralAgent(**params)


def test_resolve_memory_binding_uses_explicit_memory_ids() -> None:
    agent = _build_agent(
        memory_channel_id="telegram",
        memory_conversation_id="chat-123",
        memory_task_id="session-456",
    )

    binding = agent._resolve_context_binding("fallback-chat")

    assert binding is not None
    assert binding.namespaces == [
        "global",
        "agent:planner",
        "channel:telegram",
        "conversation:chat-123",
        "task:session-456",
    ]
    assert binding.agent_id == "planner"
    assert binding.channel_id == "telegram"
    assert binding.conversation_id == "chat-123"
    assert binding.task_id == "session-456"


def test_resolve_memory_binding_falls_back_to_runtime_values() -> None:
    agent = _build_agent()

    binding = agent._resolve_context_binding("chat-runtime")

    assert binding is not None
    assert binding.namespaces == [
        "global",
        "agent:planner",
        "channel:web_chat",
        "conversation:chat-runtime",
    ]
    assert binding.agent_id == "planner"
    assert binding.channel_id == "web_chat"
    assert binding.conversation_id == "chat-runtime"


def test_resolve_memory_binding_includes_shared_contexts() -> None:
    agent = _build_agent(memory_shared_context_ids=["customer-a", "launch-plan"])

    binding = agent._resolve_context_binding("chat-runtime")

    assert binding is not None
    assert binding.shared_context_ids == ["customer-a", "launch-plan"]
    assert binding.namespaces == [
        "global",
        "agent:planner",
        "channel:web_chat",
        "conversation:chat-runtime",
        "shared:customer-a",
        "shared:launch-plan",
    ]


# def test_resolve_memory_binding_returns_none_without_user() -> None:
#     agent = _build_agent(
#         memory_policy=AgentMemoryPolicy(
#             read_scopes=(MemoryScopeLevel.GLOBAL, MemoryScopeLevel.AGENT),
#             write_policy=MemoryWritePolicy.TASK,
#         ),
#     )
#
#     binding = agent._resolve_context_binding("chat-runtime")
#
#     assert binding is not None
#     assert binding.namespaces == [
#         "global",
#         "agent:planner",
#     ]
#     assert binding.memory_policy is not None
#     assert binding.memory_policy.write_policy == MemoryWritePolicy.TASK
#     assert binding.task_id == "runtime-task"


def test_build_runtime_context_includes_compression_intent() -> None:
    agent = _build_agent(
        user_instructions="Focus on the current coding task.",
        declared_allowed_roots=("/workspace",),
    )

    context = agent._build_runtime_context(
        query="修复 app/services/agent/agent_service.py，并检查 app.services.agent",
        chat_history=[
            HumanMessage(content="之前一直在看 app/ai_agents/general_agent/agent.py"),
            ToolMessage(content="Permission denied", tool_call_id="call_failed_9", name="bash", status="error"),
        ],
        effective_chat_id="chat-runtime",
    )

    assert context["user_instructions"] == "Focus on the current coding task."
    assert context["session_id"] == "chat_chat-runtime"
    assert context["chat_id"] == "chat-runtime"
    assert context["supports_vision"] is False
    assert context["compression_intent"] == {
        "focus_files": [
            "app/services/agent/agent_service.py",
            "app/ai_agents/general_agent/agent.py",
        ],
        "focus_modules": ["app.services.agent"],
        "failed_tool_call_ids": ["call_failed_9"],
        "user_goal_hint": "修复 app/services/agent/agent_service.py，并检查 app.services.agent",
    }


def test_build_runtime_context_propagates_compress_start_ratio() -> None:
    agent = _build_agent(
        engine_params={"compress_start_ratio": 0.65, "max_tool_calls": 10},
    )

    context = agent._build_runtime_context(
        query="hello",
        chat_history=[],
        effective_chat_id="chat-ratio-test",
    )

    assert context["compress_start_ratio"] == 0.65


def test_build_runtime_context_omits_compress_start_ratio_when_absent() -> None:
    agent = _build_agent(engine_params={"max_tool_calls": 10})

    context = agent._build_runtime_context(
        query="hello",
        chat_history=[],
        effective_chat_id="chat-no-ratio",
    )

    assert "compress_start_ratio" not in context


def test_build_runtime_context_omits_compress_start_ratio_when_none() -> None:
    agent = _build_agent(engine_params={"compress_start_ratio": None})

    context = agent._build_runtime_context(
        query="hello",
        chat_history=[],
        effective_chat_id="chat-none-ratio",
    )

    assert "compress_start_ratio" not in context


def test_build_runtime_context_no_engine_params() -> None:
    """engine_params=None (default) should not include compress_start_ratio."""
    agent = _build_agent()

    context = agent._build_runtime_context(
        query="hello",
        chat_history=[],
        effective_chat_id="chat-default",
    )

    assert "compress_start_ratio" not in context


def test_build_runtime_context_string_ratio_passthrough() -> None:
    """String ratio from JSON is passed through; harness _coerce_optional_float handles conversion."""
    agent = _build_agent(engine_params={"compress_start_ratio": "0.7"})

    context = agent._build_runtime_context(
        query="hello",
        chat_history=[],
        effective_chat_id="chat-string-ratio",
    )

    assert context["compress_start_ratio"] == "0.7"
