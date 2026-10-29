"""A platform that limits bytes gets chunks that fit in bytes: the splitter counts in the unit a channel declares."""

from __future__ import annotations

import random
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.wecom.aibot_channel import WeComAiBotChannel
from app.channels.providers.wecom.channel import WeComChannel
from app.channels.rendering.renderer import render
from app.channels.rendering.splitter import cap_stream_preview, split_message
from app.channels.routing.message_effects import MessageEffects
from app.channels.types import OutboundMessage, RenderStyle
from tests.channels.splitter_testkit import CJK_WORDS, EMPTY_FENCE, random_document, text_of


def _sizes(chunks: list[str]) -> list[int]:
    """UTF-8 sizes of the chunks; a lone surrogate counts three bytes, as the splitter counts it."""
    return [len(chunk.encode("utf-8", "surrogatepass")) for chunk in chunks]


def _reply(content: str) -> OutboundMessage:
    return OutboundMessage(channel="wecom", recipient_id="u1", user_id="u1", content=content)


class TestByteUnit:
    def test_characters_are_the_default_unit(self) -> None:
        assert RenderStyle().length_unit == "chars"
        assert [len(chunk) for chunk in split_message("你" * 100, 50)] == [50, 50]

    def test_cjk_text_is_cut_to_the_byte_limit(self) -> None:
        text = "你" * 1000
        chunks = split_message(text, 300, unit="utf8")

        assert _sizes(chunks) == [300] * 10
        assert "".join(chunks) == text

    def test_ascii_text_keeps_the_whole_limit(self) -> None:
        chunks = split_message("a" * 5000, 2048, unit="utf8")

        assert [len(chunk) for chunk in chunks] == [2048, 2048, 904]

    def test_four_byte_characters_are_counted_in_full(self) -> None:
        chunks = split_message("😀" * 100, 40, unit="utf8")

        assert [len(chunk) for chunk in chunks] == [10] * 10

    def test_mixed_widths_stay_within_the_limit_and_lose_nothing(self) -> None:
        text = "a你😀é" * 400
        chunks = split_message(text, 97, unit="utf8")

        assert max(_sizes(chunks)) <= 97
        assert "".join(chunks) == text

    def test_a_fenced_cjk_line_is_cut_and_fenced_piece_by_piece(self) -> None:
        line = "码" * 500
        chunks = split_message(f"```python\n{line}\n```", 200, unit="utf8")

        assert len(chunks) > 1
        assert max(_sizes(chunks)) <= 200
        assert all(chunk.startswith("```python\n") and chunk.endswith("\n```") for chunk in chunks)
        assert "".join(chunk.split("\n")[1] for chunk in chunks) == line

    def test_a_reopened_fence_marker_with_a_cjk_tag_is_counted_in_bytes(self) -> None:
        chunks = split_message("```代码\n" + "\n".join(["x" * 21] * 12) + "\n```", 100, unit="utf8")

        assert len(chunks) > 1
        assert max(_sizes(chunks)) <= 100
        assert all(chunk.startswith("```代码\n") and chunk.endswith("\n```") for chunk in chunks)

    def test_a_long_line_under_a_cjk_fence_tag_is_cut_by_bytes(self) -> None:
        line = "x" * 500
        chunks = split_message(f"```代码\n{line}\n```", 100, unit="utf8")

        assert max(_sizes(chunks)) <= 100
        assert "".join(chunk.split("\n")[1] for chunk in chunks) == line

    def test_a_character_dearer_than_the_limit_goes_out_alone(self) -> None:
        assert split_message("你好世", 2, unit="utf8") == ["你", "好", "世"]

    def test_a_lone_surrogate_is_counted_instead_of_rejected(self) -> None:
        chunks = split_message("a\ud800b" * 200, 50, unit="utf8")

        assert max(_sizes(chunks)) <= 50
        assert "".join(chunks) == "a\ud800b" * 200

    def test_random_documents_fit_the_byte_limit_without_empty_blocks_or_lost_text(self) -> None:
        rng = random.Random(20261031)
        for _ in range(300):
            limit = rng.choice([90, 300, 2048])
            document = random_document(rng, limit, words=CJK_WORDS, code_char="码")
            chunks = split_message(document, limit, unit="utf8")

            assert max(_sizes(chunks)) <= limit, (limit, _sizes(chunks))
            assert not any(EMPTY_FENCE.match(chunk.strip()) for chunk in chunks)
            assert text_of(chunks) == text_of([document])


class TestStreamPreview:
    def test_a_preview_is_capped_in_bytes(self) -> None:
        text = "你好，世界" * 50
        preview = cap_stream_preview(text, 100, unit="utf8")

        assert _sizes([preview])[0] <= 100
        assert preview.endswith("…")
        assert text.startswith(preview[:-1])

    def test_characters_are_the_default_unit(self) -> None:
        assert len(cap_stream_preview("你好，世界" * 50, 100)) <= 100

    def test_a_preview_within_the_limit_is_untouched(self) -> None:
        assert cap_stream_preview("你好", 6, unit="utf8") == "你好"

    def test_a_limit_below_the_ellipsis_cuts_without_it(self) -> None:
        assert cap_stream_preview("你好世界", 3, unit="utf8") == "你"

    @pytest.mark.asyncio
    async def test_a_progress_edit_is_capped_in_the_unit_the_channel_declares(self) -> None:
        channel = MagicMock()
        channel.render_style = RenderStyle(max_text_length=60, length_unit="utf8")
        channel.edit_message = AsyncMock()
        bus = MagicMock()
        bus.get_channel = MagicMock(return_value=channel)

        assert await MessageEffects(bus).edit_progress("wecom", "c1", "ph", "正在搜索资料，" * 20) is True

        (call,) = channel.edit_message.await_args_list
        assert _sizes([call.args[2]])[0] <= 60


class TestWeComLimits:
    """WeCom limits a message in bytes: 2048 for the self-built app, 20480 for the AI bot."""

    def test_a_long_chinese_reply_fits_the_app_limit_chunk_by_chunk(self) -> None:
        text = ("这是一段用来测试企业微信字节上限的中文回复，" * 200)[:3000]
        chunks = render(_reply(text), WeComChannel.render_style)

        assert len(chunks) > 1
        assert max(_sizes(chunks)) <= 2048
        assert "".join(chunks) == text

    def test_a_long_chinese_reply_fits_the_ai_bot_limit_chunk_by_chunk(self) -> None:
        text = "这是一段用来测试智能机器人字节上限的中文回复。" * 1500
        chunks = render(_reply(text), WeComAiBotChannel.render_style)

        assert len(chunks) > 1
        assert max(_sizes(chunks)) <= 20480
        assert "".join(chunks) == text

    @pytest.mark.parametrize("style", [WeComChannel.render_style, WeComAiBotChannel.render_style])
    def test_both_channels_declare_the_byte_unit(self, style: RenderStyle) -> None:
        assert style.length_unit == "utf8"
