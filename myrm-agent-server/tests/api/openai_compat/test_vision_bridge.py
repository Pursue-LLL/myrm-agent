"""Unit tests for Vision Bridge passthrough guardrail."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.openai_compat.types import ChatMessage
from app.api.openai_compat.vision_bridge import (
    _MAX_BRIDGE_IMAGES,
    _check_model_vision_support,
    bridge_vision,
    has_image_content,
)


def _text_msg(text: str) -> ChatMessage:
    return ChatMessage(role="user", content=text)


def _image_msg(b64: str = "abc123", mime: str = "image/png") -> ChatMessage:
    return ChatMessage(
        role="user",
        content=[
            {"type": "text", "text": "What is this?"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            },
        ],
    )


def _http_url_image_msg() -> ChatMessage:
    return ChatMessage(
        role="user",
        content=[
            {"type": "text", "text": "Describe this"},
            {
                "type": "image_url",
                "image_url": {"url": "https://example.com/photo.jpg"},
            },
        ],
    )


# ---------------------------------------------------------------------------
# has_image_content
# ---------------------------------------------------------------------------

class TestHasImageContent:
    def test_plain_text(self) -> None:
        assert has_image_content([_text_msg("hello")]) is False

    def test_with_image(self) -> None:
        assert has_image_content([_image_msg()]) is True

    def test_empty_messages(self) -> None:
        assert has_image_content([]) is False

    def test_mixed_messages(self) -> None:
        msgs = [_text_msg("hi"), _image_msg(), _text_msg("bye")]
        assert has_image_content(msgs) is True

    def test_content_list_without_image(self) -> None:
        msg = ChatMessage(role="user", content=[{"type": "text", "text": "no image"}])
        assert has_image_content([msg]) is False


# ---------------------------------------------------------------------------
# _check_model_vision_support
# ---------------------------------------------------------------------------

class TestCheckModelVisionSupport:
    def test_vision_model_returns_true(self) -> None:
        with patch("litellm.get_model_info", return_value={"supports_vision": True}):
            assert _check_model_vision_support("gpt-4o") is True

    def test_non_vision_model_returns_false(self) -> None:
        with patch("litellm.get_model_info", return_value={"supports_vision": False}):
            assert _check_model_vision_support("gpt-4o-mini") is False

    def test_unknown_model_fails_open(self) -> None:
        with patch("litellm.get_model_info", side_effect=Exception("unknown model")):
            assert _check_model_vision_support("custom/my-model") is True

    def test_no_vision_key_fails_open(self) -> None:
        with patch("litellm.get_model_info", return_value={}):
            assert _check_model_vision_support("some-model") is True


# ---------------------------------------------------------------------------
# bridge_vision
# ---------------------------------------------------------------------------

class TestBridgeVision:
    @pytest.mark.asyncio
    async def test_no_images_returns_original(self) -> None:
        msgs = [_text_msg("hello")]
        result = await bridge_vision(msgs, "claude-3-haiku")
        assert result is msgs

    @pytest.mark.asyncio
    async def test_bridge_disabled_returns_original(self) -> None:
        msgs = [_image_msg()]
        with patch(
            "app.api.openai_compat.vision_bridge._is_bridge_enabled",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await bridge_vision(msgs, "claude-3-haiku")
            assert result is msgs

    @pytest.mark.asyncio
    async def test_vision_model_returns_original(self) -> None:
        msgs = [_image_msg()]
        with (
            patch(
                "app.api.openai_compat.vision_bridge._is_bridge_enabled",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.openai_compat.vision_bridge._check_model_vision_support",
                return_value=True,
            ),
        ):
            result = await bridge_vision(msgs, "gpt-4o")
            assert result is msgs

    @pytest.mark.asyncio
    async def test_no_engine_returns_original(self) -> None:
        msgs = [_image_msg()]
        with (
            patch(
                "app.api.openai_compat.vision_bridge._is_bridge_enabled",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.openai_compat.vision_bridge._check_model_vision_support",
                return_value=False,
            ),
            patch(
                "app.api.openai_compat.vision_bridge._load_vision_engine",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await bridge_vision(msgs, "claude-3-haiku")
            assert result is msgs

    @pytest.mark.asyncio
    async def test_successful_bridge(self) -> None:
        msgs = [_image_msg()]
        mock_engine = MagicMock()
        mock_engine.describe_image_b64 = AsyncMock(return_value="A photo of a cat")

        with (
            patch(
                "app.api.openai_compat.vision_bridge._is_bridge_enabled",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.openai_compat.vision_bridge._check_model_vision_support",
                return_value=False,
            ),
            patch(
                "app.api.openai_compat.vision_bridge._load_vision_engine",
                new_callable=AsyncMock,
                return_value=mock_engine,
            ),
        ):
            result = await bridge_vision(msgs, "claude-3-haiku")

            assert len(result) == 1
            content = result[0].content
            assert isinstance(content, list)
            assert content[0] == {"type": "text", "text": "What is this?"}
            assert content[1]["type"] == "text"
            assert "[Image Description]" in content[1]["text"]
            assert "A photo of a cat" in content[1]["text"]

    @pytest.mark.asyncio
    async def test_description_failure_preserves_original(self) -> None:
        msgs = [_image_msg()]
        mock_engine = MagicMock()
        mock_engine.describe_image_b64 = AsyncMock(side_effect=RuntimeError("model timeout"))

        with (
            patch(
                "app.api.openai_compat.vision_bridge._is_bridge_enabled",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.openai_compat.vision_bridge._check_model_vision_support",
                return_value=False,
            ),
            patch(
                "app.api.openai_compat.vision_bridge._load_vision_engine",
                new_callable=AsyncMock,
                return_value=mock_engine,
            ),
        ):
            result = await bridge_vision(msgs, "claude-3-haiku")

            assert len(result) == 1
            content = result[0].content
            assert isinstance(content, list)
            assert content[1]["type"] == "image_url"

    @pytest.mark.asyncio
    async def test_http_url_image_preserved(self) -> None:
        msgs = [_http_url_image_msg()]
        mock_engine = MagicMock()
        mock_engine.describe_image_b64 = AsyncMock(return_value="should not be called")

        with (
            patch(
                "app.api.openai_compat.vision_bridge._is_bridge_enabled",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.openai_compat.vision_bridge._check_model_vision_support",
                return_value=False,
            ),
            patch(
                "app.api.openai_compat.vision_bridge._load_vision_engine",
                new_callable=AsyncMock,
                return_value=mock_engine,
            ),
        ):
            result = await bridge_vision(msgs, "claude-3-haiku")

            content = result[0].content
            assert isinstance(content, list)
            assert content[1]["type"] == "image_url"
            mock_engine.describe_image_b64.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_images_limit(self) -> None:
        blocks: list[dict[str, Any]] = [{"type": "text", "text": "Describe all"}]
        for i in range(_MAX_BRIDGE_IMAGES + 2):
            blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,img{i}"},
            })
        msg = ChatMessage(role="user", content=blocks)

        mock_engine = MagicMock()
        mock_engine.describe_image_b64 = AsyncMock(return_value="described")

        with (
            patch(
                "app.api.openai_compat.vision_bridge._is_bridge_enabled",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.openai_compat.vision_bridge._check_model_vision_support",
                return_value=False,
            ),
            patch(
                "app.api.openai_compat.vision_bridge._load_vision_engine",
                new_callable=AsyncMock,
                return_value=mock_engine,
            ),
        ):
            result = await bridge_vision([msg], "claude-3-haiku")

            content = result[0].content
            assert isinstance(content, list)
            described_count = sum(
                1 for b in content
                if isinstance(b, dict) and b.get("type") == "text" and "[Image Description]" in b.get("text", "")
            )
            assert described_count == _MAX_BRIDGE_IMAGES
            preserved_count = sum(
                1 for b in content if isinstance(b, dict) and b.get("type") == "image_url"
            )
            assert preserved_count == 2

    @pytest.mark.asyncio
    async def test_plain_text_message_passes_through(self) -> None:
        msgs = [_text_msg("no images"), _image_msg()]
        mock_engine = MagicMock()
        mock_engine.describe_image_b64 = AsyncMock(return_value="cat photo")

        with (
            patch(
                "app.api.openai_compat.vision_bridge._is_bridge_enabled",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.openai_compat.vision_bridge._check_model_vision_support",
                return_value=False,
            ),
            patch(
                "app.api.openai_compat.vision_bridge._load_vision_engine",
                new_callable=AsyncMock,
                return_value=mock_engine,
            ),
        ):
            result = await bridge_vision(msgs, "claude-3-haiku")

            assert result[0].content == "no images"
            content = result[1].content
            assert isinstance(content, list)
            assert any("[Image Description]" in str(b) for b in content)
