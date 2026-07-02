"""Integration: enabled_builtin_tools + provider key → image_tool in tools list."""

from __future__ import annotations

from unittest.mock import patch

from app.services.agent.params.media import _extract_media_generation_params


def test_image_generation_chain_from_enabled_builtin_tools() -> None:
    """media.py params extraction + tool_setup must produce image_tool (ADM eager mount)."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    enabled = ["image_generation"]
    providers_dict = {
        "providers": [
            {
                "id": "openai",
                "isEnabled": True,
                "apiKeys": [{"key": "sk-test-image", "isActive": True}],
            }
        ]
    }

    image_params, video_params, tts_params = _extract_media_generation_params(
        None,
        providers_dict,
        enabled,
        None,
    )

    assert image_params is not None
    assert image_params.api_key == "sk-test-image"
    assert video_params is None
    assert tts_params is None

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.image_generation_params = image_params
    tools: list[object] = []

    with patch(
        "app.ai_agents.general_agent.tool_setup._get_artifact_push_fn",
        return_value=None,
    ):
        mixin._setup_image_generation_tools(tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "image_tool"
