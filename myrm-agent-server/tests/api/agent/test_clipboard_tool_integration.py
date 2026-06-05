import pytest

from app.ai_agents.general_agent.agent import GeneralAgent


@pytest.mark.asyncio
async def test_clipboard_tool_registered():
    """Test that write_to_clipboard tool is registered in GeneralAgent."""
    # Initialize a dummy agent

    from app.core.types import ModelConfig

    agent = GeneralAgent(
        chat_id="test_chat",
        model_cfg=ModelConfig(model="test", provider="test", api_key="test"),
        mcp_config=None,
        search_service_cfg=None,
    )
    agent.declared_capabilities = ["ask_question_tool"]

    # We just need to check if the tool is in the list of tools
    tools = []
    deferred_tools = []

    # Call the setup method
    agent._setup_interaction_tools(tools, deferred_tools)

    # Verify write_to_clipboard is in the tools list
    tool_names = [getattr(t, "name", getattr(t, "__name__", str(t))) for t in tools]
    assert "write_to_clipboard_tool" in tool_names
