"""Integration: smart-routing real pipeline for media queries (no route_task mock).

Verifies the full converter → route_task wiring against the real harness
router: multimodal queries (image/video) must route to STANDARD (vision
floor), while plain-text trivial queries route to SIMPLE when a light model
is configured. route_task is NOT mocked — the only seams are model-config
resolution and the DB read of recent routing tiers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.routing.complexity_router import RoutingTier

from app.core.types import ModelConfig
from app.services.agent.params.models import AgentRequest, ModelSelection
from tests.api.agent.utils import get_model_selection

_DUMMY_KEY = "sk-test-routing"


def _lite_selection() -> dict[str, object]:
    return {"providerId": "openai", "model": "gpt-4o-mini"}


async def _fake_resolve(selection: ModelSelection, providers: dict[str, object] | None) -> ModelConfig:
    return ModelConfig(model="gpt-4o-mini", api_key=_DUMMY_KEY)


def _video_query() -> list[dict[str, object]]:
    return [
        {"type": "text", "text": "hello"},
        {"type": "video_url", "video_url": {"url": "https://example.com/v.mp4"}},
    ]


def _image_query() -> list[dict[str, object]]:
    return [
        {"type": "text", "text": "hello"},
        {"type": "image_url", "image_url": {"url": "https://example.com/i.png"}},
    ]


async def _run_converter(query: str | list[dict[str, object]]) -> str | None:
    request = AgentRequest(
        message_id="test-msg-media",
        chat_id="test-chat-media",
        query=query,
        model_selection=get_model_selection(),
        light_model_selection=_lite_selection(),
    )
    with (
        patch(
            "app.services.agent.params.converter._resolve_model_config",
            new=_fake_resolve,
        ),
        patch(
            "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        from app.services.agent.params.converter import convert_to_general_agent_params

        _, routing_tier, _, _, _ = await convert_to_general_agent_params(request, [])
    return routing_tier


class TestSmartRoutingMediaRealPipeline:
    """converter → real route_task wiring for multimodal queries."""

    @pytest.mark.asyncio
    async def test_video_query_routes_to_standard(self) -> None:
        tier = await _run_converter(_video_query())
        assert tier == RoutingTier.STANDARD.value

    @pytest.mark.asyncio
    async def test_image_query_routes_to_standard(self) -> None:
        tier = await _run_converter(_image_query())
        assert tier == RoutingTier.STANDARD.value

    @pytest.mark.asyncio
    async def test_plain_text_trivial_query_routes_to_simple(self) -> None:
        tier = await _run_converter("hi")
        assert tier == RoutingTier.SIMPLE.value

    @pytest.mark.asyncio
    async def test_no_routing_selection_skips_smart_routing(self) -> None:
        """No light/reasoning model selection → smart routing inactive, tier None."""
        request = AgentRequest(
            message_id="test-msg-noroute",
            chat_id="test-chat-noroute",
            query="hello",
            model_selection=get_model_selection(),
        )
        with (
            patch(
                "app.services.agent.params.converter._resolve_model_config",
                new=_fake_resolve,
            ),
        ):
            from app.services.agent.params.converter import (
                convert_to_general_agent_params,
            )

            _, routing_tier, _, _, _ = await convert_to_general_agent_params(request, [])
        assert routing_tier is None

    @pytest.mark.asyncio
    async def test_image_query_with_min_tier_stays_standard(self) -> None:
        """complaint-up min_tier + image query: media floor already STANDARD, no downgrade."""
        request = AgentRequest(
            message_id="test-msg-complaint-image",
            chat_id="test-chat-complaint-image",
            query=_image_query(),
            model_selection=get_model_selection(),
            light_model_selection=_lite_selection(),
            sibling_group_id="sib-complaint-image",
        )
        with (
            patch(
                "app.services.agent.params.converter._resolve_model_config",
                new=_fake_resolve,
            ),
            patch(
                "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
                new_callable=AsyncMock,
                return_value=["simple"],
            ),
        ):
            from app.services.agent.params.converter import (
                convert_to_general_agent_params,
            )

            _, routing_tier, _, _, _ = await convert_to_general_agent_params(request, [])
        # complaint-up 会对上一档 SIMPLE 记一次真实 misroute（O6 只跳过 REASONING），
        # 测试后清理全局 penalty 以免污染后续 SIMPLE 判定。
        from myrm_agent_harness.toolkits.llms.routing.complexity_router import (
            get_penalty_tracker,
        )

        get_penalty_tracker()._flags.pop("simple", None)
        assert routing_tier == RoutingTier.STANDARD.value
