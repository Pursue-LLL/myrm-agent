"""The interactive cards the Feishu channel sends: placeholder, component, result, contact and deliverable cards."""

from __future__ import annotations

import pytest

from app.channels.providers.feishu.cards import (
    build_component_card,
    build_contact_disambiguation_card,
    build_deliverable_card,
    build_result_card,
    wrap_text_as_card,
)
from app.channels.providers.feishu.cards.builders import CARD_CONFIG
from app.channels.types import OutboundMessage, QuickReply


def _message(**overrides: object) -> OutboundMessage:
    fields: dict[str, object] = {"channel": "feishu", "recipient_id": "oc_1", "content": "x", "user_id": "u1"}
    fields.update(overrides)
    return OutboundMessage(**fields)


def _elements(card: dict[str, object]) -> list[dict[str, object]]:
    elements = card["elements"]
    assert isinstance(elements, list)
    return elements


def _tags(card: dict[str, object]) -> list[object]:
    return [element["tag"] for element in _elements(card)]


def _note(card: dict[str, object]) -> str | None:
    """The text of the note under the card body, if the card has one."""
    notes = [element for element in _elements(card) if element["tag"] == "note"]
    return notes[0]["elements"][0]["content"] if notes else None


def _sources_text(card: dict[str, object]) -> str:
    """The sources block, which sits right below the divider."""
    elements = _elements(card)
    divider = next(index for index, element in enumerate(elements) if element["tag"] == "hr")
    return str(elements[divider + 1]["text"]["content"])


def test_every_card_config_lets_the_card_be_updated_in_place() -> None:
    assert CARD_CONFIG["update_multi"] is True
    for card in (wrap_text_as_card("t"), build_result_card("t"), build_deliverable_card("t", "s")):
        assert card["config"] == CARD_CONFIG


def test_a_placeholder_is_a_single_markdown_block() -> None:
    assert wrap_text_as_card("Thinking...") == {
        "config": CARD_CONFIG,
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": "Thinking..."}}],
    }


class TestComponentCard:
    def test_a_message_without_interactive_elements_needs_no_card(self) -> None:
        assert build_component_card(_message(), "text") is None

    def test_quick_replies_follow_the_text(self) -> None:
        card = build_component_card(_message(quick_replies=(QuickReply(label="Yes", text="yes"),)), "Pick one")

        assert card is not None
        assert _elements(card)[0] == {"tag": "markdown", "content": "Pick one"}
        assert _tags(card) == ["markdown", "action"]

    def test_a_card_without_text_holds_only_the_actions(self) -> None:
        card = build_component_card(_message(quick_replies=(QuickReply(label="Yes", text="yes"),)), "")

        assert card is not None
        assert _tags(card) == ["action"]

    def test_fallback_options_alone_make_a_card(self) -> None:
        option = {"tag": "div", "text": {"tag": "lark_md", "content": "[1] Approve"}}

        card = build_component_card(_message(), "", fallback_options=[option])

        assert card == {"config": CARD_CONFIG, "elements": [option]}


class TestResultCard:
    def test_a_card_of_content_alone_has_no_header_and_no_note(self) -> None:
        assert build_result_card("answer") == {
            "config": CARD_CONFIG,
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": "answer"}}],
        }

    def test_no_content_leaves_no_block(self) -> None:
        assert _elements(build_result_card("")) == []

    def test_sources_are_numbered_like_the_citations_in_the_content(self) -> None:
        card = build_result_card(
            "see [1] and [7]",
            sources=[{"url": "https://a.dev", "title": "A"}, {"url": "https://b.dev", "title": "B", "index": 7}],
        )

        assert _tags(card) == ["div", "hr", "div"]
        assert _sources_text(card) == "**Sources**\n[1] [A](https://a.dev)\n[7] [B](https://b.dev)"

    def test_a_source_without_a_url_is_skipped_but_keeps_its_place(self) -> None:
        sources = [{"url": "https://a.dev", "title": "A"}, {"title": "dead"}, {"url": "https://c.dev"}]

        assert _sources_text(build_result_card("c", sources=sources)) == (
            "**Sources**\n[1] [A](https://a.dev)\n[3] [https://c.dev](https://c.dev)"
        )

    def test_sources_without_any_url_leave_no_divider_behind(self) -> None:
        card = build_result_card("c", sources=[{"title": "dead"}, {"title": "also dead"}])

        assert _tags(card) == ["div"]

    def test_at_most_ten_sources_are_listed(self) -> None:
        sources = [{"url": f"https://s{i}.dev", "title": f"S{i}"} for i in range(12)]

        listed = _sources_text(build_result_card("c", sources=sources)).split("\n")[1:]

        assert len(listed) == 10
        assert listed[-1] == "[10] [S9](https://s9.dev)"

    @pytest.mark.parametrize(
        ("success", "template"),
        [(True, "green"), (False, "red"), (None, "blue")],
    )
    def test_the_header_colour_follows_the_outcome(self, success: bool | None, template: str) -> None:
        card = build_result_card("c", title="Nightly report", success=success)

        assert card["header"] == {"title": {"tag": "plain_text", "content": "Nightly report"}, "template": template}

    def test_an_outcome_without_a_title_is_a_notification(self) -> None:
        header = build_result_card("c", success=False)["header"]

        assert header["title"]["content"] == "Notification"

    def test_a_card_without_title_or_outcome_has_no_header(self) -> None:
        assert "header" not in build_result_card("c", timestamp="2026-11-13 10:00 UTC")

    def test_the_note_joins_the_timestamp_and_the_cost(self) -> None:
        card = build_result_card(
            "c",
            timestamp="2026-11-13 10:00 UTC",
            cost_metadata={"cost_usd": 0.0123, "model_name": "gpt-5", "total_tokens": 1500},
        )

        assert _note(card) == "2026-11-13 10:00 UTC · gpt-5 · 1.5k tokens · ~$0.0123"

    @pytest.mark.parametrize(
        ("cost_metadata", "note"),
        [
            ({"cost_usd": 0.5, "total_tokens": 999}, "999 tokens · ~$0.5000"),
            ({"cost_usd": 0.5, "total_tokens": 1000}, "1.0k tokens · ~$0.5000"),
            ({"cost_usd": 0.5, "total_tokens": 0, "model_name": ""}, "~$0.5000"),
            ({"cost_usd": 2, "model_name": "m", "total_tokens": "many"}, "m · ~$2.0000"),
        ],
    )
    def test_the_cost_note_lists_only_what_the_metadata_holds(self, cost_metadata: dict[str, object], note: str) -> None:
        assert _note(build_result_card("c", cost_metadata=cost_metadata)) == note

    @pytest.mark.parametrize("cost_usd", [0, -1.0, "free", None])
    def test_a_cost_that_is_not_a_positive_number_adds_no_note(self, cost_usd: object) -> None:
        assert _note(build_result_card("c", cost_metadata={"cost_usd": cost_usd, "model_name": "m"})) is None


class TestContactDisambiguationCard:
    def test_each_candidate_is_a_button_that_carries_the_contact(self) -> None:
        card = build_contact_disambiguation_card(
            "Zhang",
            [{"name": "Zhang San", "department": "R&D", "open_id": "ou_1"}, {"name": "Zhang Wei", "open_id": "ou_2"}],
        )

        assert "Zhang" in str(_elements(card)[0]["content"])
        buttons = _elements(card)[1]["actions"]
        assert [button["text"]["content"] for button in buttons] == ["Zhang San (R&D)", "Zhang Wei"]
        assert buttons[1]["value"] == {"action": "select_contact", "open_id": "ou_2", "name": "Zhang Wei"}

    def test_at_most_five_candidates_are_offered(self) -> None:
        candidates = [{"name": f"Zhang {i}", "open_id": f"ou_{i}"} for i in range(8)]

        card = build_contact_disambiguation_card("Zhang", candidates, action_key="pick")

        buttons = _elements(card)[1]["actions"]
        assert len(buttons) == 5
        assert buttons[0]["value"]["action"] == "pick"

    def test_no_candidates_leave_only_the_question(self) -> None:
        card = build_contact_disambiguation_card("Nobody", [])

        assert _tags(card) == ["markdown"]
        assert card["header"]["template"] == "blue"


class TestDeliverableCard:
    def test_the_file_and_the_table_each_get_a_link_button(self) -> None:
        card = build_deliverable_card(
            "Q3 report", "Revenue is up", file_name="q3.pdf", file_url="https://f.dev/q3", bitable_url="https://b.dev/t"
        )

        assert _elements(card)[0]["content"] == "**Q3 report**\n\nRevenue is up"
        buttons = _elements(card)[1]["actions"]
        assert [(button["type"], button["url"]) for button in buttons] == [
            ("primary", "https://f.dev/q3"),
            ("default", "https://b.dev/t"),
        ]
        assert "q3.pdf" in buttons[0]["text"]["content"]

    def test_only_the_links_given_become_buttons(self) -> None:
        card = build_deliverable_card("T", "S", file_url="https://f.dev/x")

        buttons = _elements(card)[1]["actions"]
        assert len(buttons) == 1
        assert buttons[0]["text"]["content"].endswith("查看附件")

    def test_a_deliverable_without_links_is_a_summary_only(self) -> None:
        assert _tags(build_deliverable_card("T", "S")) == ["markdown"]
