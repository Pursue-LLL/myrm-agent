"""E2E Test for Unified Capability Discovery Gateway."""


import pytest
from langchain_core.tools import BaseTool
from myrm_agent_harness.agent.base_agent import BaseAgent
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.types import AgentRuntimeConfig
from pydantic import BaseModel, Field


@pytest.mark.asyncio
async def test_discover_capability_e2e_real_model():
    """
    Test that the agent can use discover_capability to find a tool.
    The auto-mount execution path is covered by middleware unit tests,
    while this real-model E2E verifies prompt adherence and surfaced output.

    Uses BaseAgent (not SkillAgent) so the model only sees ``discover_capability``
    plus the deferred dummy tool — no bash/file meta-tools that would allow bypass.
    Discover + deferred registration follows ``agent_runtime.build_tools``.
    """

    class DummyInput(BaseModel):
        arg1: str = Field(description="A dummy argument")

    class DummyDeferredTool(BaseTool):
        name: str = "dummy_native_tool"
        description: str = (
            "A dummy native tool for testing. Use this tool if the user asks to test the dummy capability."
        )
        args_schema: type[BaseModel] = DummyInput

        def _run(self, arg1: str) -> str:
            return f"Dummy tool executed with arg: {arg1}"

    import os

    from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model

    from tests.api.agent.utils import _convert_litellm_model

    api_key = os.environ.get("BASIC_API_KEY", "").strip()
    if not api_key:
        pytest.skip(
            "BASIC_API_KEY not found in environment (see myrm-agent-server/.env.test)"
        )

    base_url = (os.environ.get("BASIC_BASE_URL") or "").strip() or None
    raw_model = (
        os.environ.get("DISCOVER_CAPABILITY_E2E_MODEL")
        or os.environ.get("BASIC_MODEL")
        or "gpt-4o-mini"
    ).strip()
    
    llm = create_litellm_model(
        model=_convert_litellm_model(raw_model),
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )

    agent = BaseAgent(
        llm=llm,
        deferred_tools=[DummyDeferredTool()],
        system_prompt=(
            'You are a helpful assistant. Use discover_capability with query "*" to list '
            "all deferred tools, then summarize the tool names you found. Do not call any "
            "other tool in this test."
        ),
        config=AgentRuntimeConfig(parallel_tool_calls=False),
    )

    tool_calls_made: list[str] = []
    message_chunks: list[str] = []

    async for event in agent.run(
        "List deferred tools with discover_capability using query `*`.",
        context={
            "session_id": "test_session_123",
            "workspaces_storage_root": "/tmp/myrm_test_workspaces",
        },
    ):
        et = event.get("type")
        print(f"EVENT TYPE: {et}")
        if et == AgentEventType.TASKS_STEPS.value:
            tn = event.get("tool_name")
            print(f"TOOL NAME: {tn}")
            if tn:
                tool_calls_made.append(str(tn))
        elif et == AgentEventType.MESSAGE.value and isinstance(event.get("data"), str):
            message_chunks.append(event["data"])

    final_response = "".join(message_chunks).strip() or None

    discover_hits = {"discover_capability_tool"}
    assert any(
        name in discover_hits for name in tool_calls_made
    ), f"Agent did not call discover_capability (got {tool_calls_made!r})"

    lower = (final_response or "").lower()
    assert final_response is not None, "Agent did not produce a final response"
    assert (
        "dummy_native_tool" in lower or "autmounttools" in lower or "autmount" in lower
    ), f"Unexpected final response: {final_response!r}"
