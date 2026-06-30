"""E2E integration test for cost metadata rendering pipeline.

Verifies the full channel rendering pipeline: when cost_metadata is present
in OutboundMessage metadata, the renderer produces the expected cost footer.
This tests the complete render() pipeline without mocking.
"""

from __future__ import annotations

import pytest

from app.channels.rendering.renderer import render
from app.channels.types import OutboundMessage, RenderStyle


def _make_outbound_with_cost(
    cost_usd: float = 0.0035,
    model_name: str = "claude-sonnet-4-20250514",
    total_tokens: int = 2500,
) -> OutboundMessage:
    return OutboundMessage(
        channel="feishu",
        recipient_id="user-123",
        content="This is the agent response.",
        user_id="U1",
        metadata={
            "cost_metadata": {
                "cost_usd": cost_usd,
                "model_name": model_name,
                "total_tokens": total_tokens,
            },
        },
    )


def _default_style(**overrides: object) -> RenderStyle:
    defaults: dict[str, object] = {
        "format": "markdown",
        "max_text_length": 4096,
        "supports_links": True,
        "supports_code_fence": True,
        "supports_latex": True,
        "supports_tables": True,
        "use_emoji": True,
    }
    defaults.update(overrides)
    return RenderStyle(**defaults)  # type: ignore[arg-type]


class TestCostMetadataRenderIntegration:
    """Integration tests for full render pipeline with cost metadata."""

    def test_full_render_includes_cost_footer(self) -> None:
        """Complete render() call produces cost footer in output."""
        msg = _make_outbound_with_cost()
        result = render(msg, _default_style())
        combined = "".join(result)
        assert "claude-sonnet-4-20250514" in combined
        assert "2.5k tokens" in combined
        assert "~$0.0035" in combined
        assert "💰" in combined

    def test_full_render_no_cost_when_zero(self) -> None:
        """Zero cost should not produce any cost footer."""
        msg = OutboundMessage(
            channel="telegram",
            recipient_id="user-456",
            content="Response without cost",
            user_id="U2",
            metadata={"cost_metadata": {"cost_usd": 0, "model_name": "x", "total_tokens": 100}},
        )
        result = render(msg, _default_style())
        combined = "".join(result)
        assert "~$" not in combined

    def test_full_render_no_metadata_field(self) -> None:
        """Message without metadata should render cleanly."""
        msg = OutboundMessage(
            channel="slack",
            recipient_id="user-789",
            content="Plain message",
            user_id="U3",
        )
        result = render(msg, _default_style())
        combined = "".join(result)
        assert combined == "Plain message"
        assert "~$" not in combined

    def test_full_render_cost_disabled_no_emoji(self) -> None:
        """With use_emoji=False, no emoji prefix but cost data still present."""
        msg = _make_outbound_with_cost(cost_usd=0.012, model_name="gpt-4o", total_tokens=8000)
        result = render(msg, _default_style(use_emoji=False))
        combined = "".join(result)
        assert "💰" not in combined
        assert "gpt-4o" in combined
        assert "8.0k tokens" in combined
        assert "~$0.0120" in combined

    def test_feishu_card_cost_note_integration(self) -> None:
        """build_result_card with cost_metadata produces a note element."""
        from app.channels.providers.feishu.cards import build_result_card

        card = build_result_card(
            "Agent response content",
            timestamp="2025-01-01 12:00 UTC",
            cost_metadata={
                "cost_usd": 0.005,
                "model_name": "claude-sonnet-4-20250514",
                "total_tokens": 3000,
            },
        )
        elements = card.get("elements", [])
        note_elements = [e for e in elements if e.get("tag") == "note"]
        assert len(note_elements) == 1

        note_content = note_elements[0]["elements"][0]["content"]
        assert "claude-sonnet-4-20250514" in note_content
        assert "$0.0050" in note_content
        assert "3.0k" in note_content
        assert "2025-01-01 12:00 UTC" in note_content

    def test_feishu_card_no_cost_no_extra_note(self) -> None:
        """Without cost_metadata, note only shows timestamp."""
        from app.channels.providers.feishu.cards import build_result_card

        card = build_result_card(
            "Response",
            timestamp="2025-06-30 10:00 UTC",
            cost_metadata=None,
        )
        elements = card.get("elements", [])
        note_elements = [e for e in elements if e.get("tag") == "note"]
        assert len(note_elements) == 1
        note_content = note_elements[0]["elements"][0]["content"]
        assert note_content == "2025-06-30 10:00 UTC"
        assert "$" not in note_content

    @pytest.mark.parametrize("cost_usd,expected_fragment", [
        (0.0001, "~$0.0001"),
        (0.1234, "~$0.1234"),
        (1.5, "~$1.5000"),
    ])
    def test_cost_precision_formatting(self, cost_usd: float, expected_fragment: str) -> None:
        """Verify cost is always formatted to 4 decimal places."""
        msg = _make_outbound_with_cost(cost_usd=cost_usd, total_tokens=100)
        result = render(msg, _default_style(use_emoji=False))
        combined = "".join(result)
        assert expected_fragment in combined

    def test_cost_footer_does_not_affect_message_splitting(self) -> None:
        """Long content + cost footer should split cleanly without corrupting footer."""
        long_content = "A" * 3000
        msg = OutboundMessage(
            channel="telegram",
            recipient_id="user-split",
            content=long_content,
            user_id="U4",
            metadata={"cost_metadata": {"cost_usd": 0.05, "model_name": "gpt-4o", "total_tokens": 5000}},
        )
        style = _default_style(max_text_length=2048)
        result = render(msg, style)
        combined = "".join(result)
        assert "~$0.0500" in combined
        assert "gpt-4o" in combined

    def test_feishu_card_with_sources_and_cost(self) -> None:
        """Cost note coexists with sources section in Feishu card."""
        from app.channels.providers.feishu.cards import build_result_card

        card = build_result_card(
            "Answer with sources",
            sources=[{"url": "https://example.com", "title": "Source 1"}],
            timestamp="2025-06-30 12:00 UTC",
            cost_metadata={"cost_usd": 0.003, "model_name": "claude-sonnet-4-20250514", "total_tokens": 1500},
        )
        elements = card.get("elements", [])
        tags = [e.get("tag") for e in elements]
        assert "hr" in tags
        assert "note" in tags
        note_el = next(e for e in elements if e.get("tag") == "note")
        note_text = note_el["elements"][0]["content"]
        assert "2025-06-30 12:00 UTC" in note_text
        assert "$0.0030" in note_text

    def test_render_with_other_metadata_fields(self) -> None:
        """cost_metadata coexists with other metadata like sources."""
        msg = OutboundMessage(
            channel="slack",
            recipient_id="user-multi-meta",
            content="Response with sources",
            user_id="U5",
            metadata={
                "sources": [{"url": "https://test.com", "title": "Test", "index": 1}],
                "cost_metadata": {"cost_usd": 0.002, "model_name": "gpt-4o-mini", "total_tokens": 800},
            },
        )
        result = render(msg, _default_style(use_emoji=False))
        combined = "".join(result)
        assert "~$0.0020" in combined
        assert "gpt-4o-mini" in combined

    def test_negative_cost_not_rendered(self) -> None:
        """Negative cost_usd should be treated as invalid and not rendered."""
        msg = OutboundMessage(
            channel="telegram",
            recipient_id="user-neg",
            content="Hello",
            user_id="U6",
            metadata={"cost_metadata": {"cost_usd": -0.001, "model_name": "x", "total_tokens": 100}},
        )
        result = render(msg, _default_style())
        combined = "".join(result)
        assert "~$" not in combined

    def test_non_dict_cost_metadata_ignored(self) -> None:
        """If cost_metadata is not a dict, it should be silently ignored."""
        msg = OutboundMessage(
            channel="telegram",
            recipient_id="user-bad-type",
            content="Hello",
            user_id="U7",
            metadata={"cost_metadata": "invalid"},
        )
        result = render(msg, _default_style())
        combined = "".join(result)
        assert combined == "Hello"
        assert "~$" not in combined
