"""What an external CLI agent is sent for a user turn: text only, nothing of our own routing."""

from __future__ import annotations

import pytest

from app.services.external_agents.delegation_prompt import delegation_prompt

_DATA_URL = "data:image/png;base64," + "iVBORw0KGgo" * 40


def _text(text: str) -> dict[str, object]:
    return {"type": "text", "text": text}


def _image(url: str, **extra: object) -> dict[str, object]:
    return {"type": "image_url", "image_url": {"url": url}, **extra}


def test_a_plain_message_is_sent_as_it_is() -> None:
    assert delegation_prompt("  fix the build\n") == "  fix the build\n"


def test_text_blocks_are_joined_into_paragraphs_and_empty_ones_dropped() -> None:
    query = [_text("compare these"), _text(""), _text("[File: notes.md]\n# Notes")]

    assert delegation_prompt(query) == "compare these\n\n[File: notes.md]\n# Notes"


def test_an_image_on_disk_is_pointed_at_by_its_path() -> None:
    query = [_text("what is in this?"), _image("file:///Users/me/Desktop/shot%20one.png")]

    assert delegation_prompt(query) == "what is in this?\n\n[Image: /Users/me/Desktop/shot one.png]"


def test_a_file_url_is_decoded_once() -> None:
    assert delegation_prompt([_image("file:///tmp/100%2525.png")]) == "[Image: /tmp/100%25.png]"


def test_a_remote_image_is_pointed_at_by_its_address() -> None:
    assert delegation_prompt([_image("https://example.com/a.png?x=1")]) == "[Image: https://example.com/a.png?x=1]"


def test_a_video_is_named_as_one() -> None:
    assert delegation_prompt([_image("file:///tmp/clip.mp4", _mime_type="video/mp4")]) == "[Video: /tmp/clip.mp4]"


def test_inline_image_data_is_not_pasted_into_the_prompt() -> None:
    prompt = delegation_prompt([_text("look"), _image(_DATA_URL)])

    assert prompt == "look\n\n[Image attached inline: its data was not forwarded to this agent]"
    assert "base64" not in prompt


def test_an_image_url_given_as_a_bare_string_is_understood() -> None:
    assert delegation_prompt([{"type": "image_url", "image_url": "https://example.com/a.png"}]) == (
        "[Image: https://example.com/a.png]"
    )


@pytest.mark.parametrize(
    "part",
    [
        {"type": "image_url", "image_url": {}},
        {"type": "image_url", "image_url": {"url": ""}},
        {"type": "text", "text": None},
        {"type": "input_audio", "input_audio": {"data": "AAAA"}},
        {"text": "no type"},
        "a bare string",
        7,
        None,
    ],
)
def test_a_block_that_says_nothing_to_a_text_prompt_is_dropped_without_leaking_its_repr(part: object) -> None:
    assert delegation_prompt([_text("hello"), part]) == "hello"


def test_a_quoted_passage_leads_the_prompt_the_way_the_main_agent_gets_it() -> None:
    assert delegation_prompt("why?", "the build failed on CI") == (
        "<quoted_context>\nthe build failed on CI\n</quoted_context>\n\nwhy?"
    )


def test_a_quote_goes_in_front_of_a_multimodal_turn_too() -> None:
    prompt = delegation_prompt([_text("explain"), _image("https://example.com/a.png")], "line one\nline two")

    assert prompt == ("<quoted_context>\nline one\nline two\n</quoted_context>\n\nexplain\n\n[Image: https://example.com/a.png]")


@pytest.mark.parametrize("quote", [None, "", "  \n "])
def test_no_quote_adds_nothing(quote: str | None) -> None:
    assert delegation_prompt("why?", quote) == "why?"


def test_a_turn_of_another_shape_is_sent_as_its_text() -> None:
    assert delegation_prompt(42) == "42"
