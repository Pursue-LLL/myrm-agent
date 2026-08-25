"""WebUI raw /learn messages must rewrite before force_skill_manage detection."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.channel_bridge.learn_handler import rewrite_learn_query_if_needed
from app.services.agent.params.converter import (
    _is_learn_skill_authoring_query,
    convert_to_general_agent_params,
)
from app.services.agent.params.models import AgentRequest
from tests.api.agent.conftest import _build_mock_user_configs
from tests.api.agent.utils import get_model_selection


def test_raw_webui_learn_triggers_force_skill_manage_gate() -> None:
    raw = (
        "/learn https://docs.example.com/webhooks focus on signature verification only"
    )
    rewritten = rewrite_learn_query_if_needed(raw)
    assert _is_learn_skill_authoring_query(rewritten) is True
    assert isinstance(rewritten, str)
    assert "focus on signature verification only" in rewritten


def test_plain_chat_does_not_trigger_force_skill_manage() -> None:
    assert _is_learn_skill_authoring_query("/learn from this chat") is False


def test_rewritten_multimodal_learn_triggers_gate() -> None:
    query: list[dict[str, str]] = [
        {"type": "text", "text": "/learn ./scripts/deploy.sh"},
    ]
    rewritten = rewrite_learn_query_if_needed(query)
    assert _is_learn_skill_authoring_query(rewritten) is True


class TestLearnWebuiConverterIntegration:
    @pytest.mark.asyncio
    async def test_explore_preset_raw_learn_rewrites_and_elevates_skill_manage(
        self,
    ) -> None:
        request = AgentRequest(
            message_id="test-msg-learn-explore",
            chat_id="test-chat-learn-explore",
            query="/learn the deployment workflow we just did",
            model_selection=get_model_selection(),
            action_mode="agent",
            security_preset="explore",
        )

        mock_configs = _build_mock_user_configs()
        with patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ):
            params, _, _, _, _ = await convert_to_general_agent_params(request, [])

        assert params.force_skill_manage is True
        assert isinstance(params.query, str)
        assert params.query.startswith("[/learn]")
        assert "skill_manage_tool" in params.query
        assert "Myrm-tool framing" in params.query

        security_config = params.security_config_raw
        assert isinstance(security_config, dict)
        permissions = security_config.get("permissions")
        assert isinstance(permissions, dict)
        assert permissions.get("file_write") == "deny"
        assert permissions.get("skill_manage") == "ask"
