import random
import re

import pytest

from app.channels.providers.telegram.html_converter import _utf16_len, split_markdown_rich, split_message

# A splitter that stops making progress appends chunks forever: fail fast instead of growing memory for minutes.
pytestmark = pytest.mark.timeout(10)

_TAG_RE = re.compile(r"</?([a-z]+)(?:\s[^>]*)?>")
_EMOJI = "\U0001f600"


def _text_of(markup: str) -> str:
    """What a reader sees: the markup with every tag taken out."""
    return _TAG_RE.sub("", markup)


def _is_balanced(markup: str) -> bool:
    """Every tag a chunk opens it also closes, innermost first."""
    open_tags: list[str] = []
    for tag in _TAG_RE.finditer(markup):
        if tag[0].startswith("</"):
            if not open_tags or open_tags.pop() != tag[1]:
                return False
        else:
            open_tags.append(tag[1])
    return not open_tags


@pytest.mark.parametrize(
    ("text", "units"),
    [("", 0), ("abc", 3), ("é", 1), ("中文", 2), (_EMOJI, 2), (f"a{_EMOJI}b", 4)],
    ids=["empty", "ascii", "latin-accent", "cjk", "emoji", "mixed"],
)
def test_utf16_len_counts_code_units_not_characters(text, units):
    assert _utf16_len(text) == units


def test_split_message_simple():
    text = "Hello " * 1000  # 6000 characters
    chunks = split_message(text, limit=4096)
    assert len(chunks) == 2
    assert _utf16_len(chunks[0]) <= 4096
    assert _utf16_len(chunks[1]) <= 4096
    assert "".join(chunks) == text


def test_split_message_with_tags():
    # A long message inside a <pre><code> block
    text = "<pre><code>" + "A" * 4090 + "B" * 100 + "</code></pre>"
    chunks = split_message(text, limit=4096)

    assert len(chunks) == 2

    # First chunk should close the tags
    assert chunks[0].startswith("<pre><code>")
    assert chunks[0].endswith("</code></pre>")
    assert _utf16_len(chunks[0]) <= 4096

    # Second chunk should reopen the tags
    assert chunks[1].startswith("<pre><code>")
    assert chunks[1].endswith("</code></pre>")
    assert _utf16_len(chunks[1]) <= 4096


def test_split_message_with_nested_tags():
    text = "<b>bold <i>italic " + "X" * 4090 + "</i></b>"
    chunks = split_message(text, limit=4096)

    assert len(chunks) == 2

    # First chunk should close <i> then <b>
    assert chunks[0].endswith("</i></b>")

    # Second chunk should reopen <b> then <i>
    assert chunks[1].startswith("<b><i>")
    assert chunks[1].endswith("</i></b>")


def test_split_message_utf16_emoji():
    # An emoji like  takes 2 UTF-16 code units
    emoji = "\U0001f600"
    assert _utf16_len(emoji) == 2

    # Create a string that is exactly 4095 code units long, then add an emoji
    # 4095 = 4095 'A's. Adding emoji makes it 4097, which exceeds 4096.
    text = "A" * 4095 + emoji
    chunks = split_message(text, limit=4096)

    assert len(chunks) == 2
    assert chunks[0] == "A" * 4095
    assert chunks[1] == emoji


def test_split_message_with_fake_tags():
    # Test that non-Telegram tags are treated as plain text and don't break the state machine
    text = "<b>bold</b> I love <3 you and <unknown> tags " * 200
    chunks = split_message(text, limit=4096)

    assert len(chunks) == 3
    # If <3 was treated as a tag, it would be closed at the end of chunk 1.
    # Since it's plain text, chunk 1 should just end with some text or a valid closing tag if it happened to split there.
    # We just ensure it doesn't crash and splits correctly.
    assert _utf16_len(chunks[0]) <= 4096
    assert _utf16_len(chunks[1]) <= 4096
    assert _utf16_len(chunks[2]) <= 4096


def test_split_message_smart_breakpoints():
    # Test that the algorithm prefers paragraph/sentence boundaries over hard splits

    # Create a text that is ~4100 chars long.
    # It has a paragraph break at 4000, a sentence break at 4050, and a space at 4080.

    part1 = "A" * 4000
    part2 = "B" * 48 + ". "
    part3 = "C" * 28 + " "
    part4 = "D" * 20

    text = part1 + "\n\n" + part2 + part3 + part4

    chunks = split_message(text, limit=4096)

    assert len(chunks) == 2

    # The split should happen at the paragraph boundary (\n\n) because it's the highest priority
    # Wait, the algorithm searches backwards from the limit (4096).
    # At 4096, the text is part1 + "\n\n" + part2 + part3 + "D"*14
    # It will search backwards for \n\n. The \n\n is at index 4000.
    # So the first chunk should end exactly after the \n\n.
    assert chunks[0] == part1 + "\n\n"
    assert chunks[1] == part2 + part3 + part4


def test_split_message_prefers_a_sentence_end_near_the_limit():
    assert split_message("A" * 3500 + ". " + "B" * 1000) == ["A" * 3500 + ". ", "B" * 1000]


def test_split_message_prefers_bare_cjk_punctuation_near_the_limit():
    assert split_message("A" * 3500 + "。" + "B" * 1000) == ["A" * 3500 + "。", "B" * 1000]


def test_split_message_limit_below_one_unit_makes_a_chunk_per_character():
    assert split_message("abc", limit=0) == ["a", "b", "c"]


def test_split_message_character_wider_than_the_limit_goes_alone():
    assert split_message(_EMOJI * 2, limit=1) == [_EMOJI, _EMOJI]


def test_split_message_character_that_does_not_fit_starts_the_next_chunk_with_the_tags_reopened():
    # <b>x<i> and its closers take 15 of 16 units, so the emoji (two units) cannot join them
    assert split_message(f"<b>x<i>{_EMOJI}</i></b>", limit=16) == ["<b>x<i></i></b>", f"<b><i>{_EMOJI}</i></b>"]


def test_split_message_chunk_filled_by_an_opening_tag_continues_in_the_next_one():
    chunks = split_message("ab<b>cdefg</b>", limit=9)
    assert all(_utf16_len(chunk) <= 9 and _is_balanced(chunk) for chunk in chunks)
    assert "".join(_text_of(chunk) for chunk in chunks) == "abcdefg"
    assert all(chunk.startswith("<b>") for chunk in chunks[1:])


@pytest.mark.parametrize(
    "text",
    [
        "x" * 30 + "</b>" + "y" * 30,
        "<b>" + "x" * 20 + "<i>" + "y" * 20 + "</b>" + "z" * 20 + "</i>",
        "<b>" + "x" * 30 + "</b>" + "<>" + "<i>" + "y" * 30 + "</i>",
    ],
    ids=["closing tag that closes nothing", "misnested tags", "angle brackets that are no tag"],
)
def test_split_message_tolerates_markup_that_is_not_well_formed(text):
    chunks = split_message(text, limit=40)
    assert all(_utf16_len(chunk) <= 40 for chunk in chunks)
    assert "".join(_text_of(chunk) for chunk in chunks) == _text_of(text)


def test_split_markdown_rich_stops_when_only_newlines_are_left():
    assert split_markdown_rich("A" * 15 + "\n\n", limit=16) == ["A" * 15 + "\n"]


# Reopening the open tags in every chunk costs their text and their closers. A stack that leaves no room for a character
# would make every chunk hold nothing but tags, so the splitter drops the tags that no longer fit.


def test_split_message_drops_a_tag_that_leaves_no_room_for_one_character():
    # "<b>" and its closer take 7 of 8 units: not even an emoji fits beside them
    assert split_message(f"<b>{_EMOJI}</b>", limit=8) == [_EMOJI]


def test_split_message_tags_that_are_all_dropped_leave_nothing_to_send():
    assert split_message("<b>" * 4, limit=8) == []


def test_split_message_keeps_the_outer_tags_and_drops_the_inner_one_that_does_not_fit():
    chunks = split_message("<b><i><u>" + "x" * 30 + "</u></i></b>", limit=20)
    assert chunks == ["<b><i>" + "x" * 6 + "</i></b>"] * 5


@pytest.mark.timeout(5)
def test_split_message_text_inside_hundreds_of_open_tags_still_goes_out():
    words = "hello world " * 600
    chunks = split_message("<b>" * 700 + words, limit=4096)
    assert all(_utf16_len(chunk) <= 4096 and _is_balanced(chunk) for chunk in chunks)
    assert "".join(_text_of(chunk) for chunk in chunks) == words


_TAGS = ("b", "i", "u", "s", "code", "pre")
_PIECES = ("a", "bc", "word ", " ", ". ", "。", "\n", "\n\n", "代码", _EMOJI, "x" * 12)


def _random_markup(rng: random.Random, depth: int = 0) -> str:
    parts: list[str] = []
    for _ in range(rng.randint(1, 5)):
        if depth < 6 and rng.random() < 0.4:
            tag = rng.choice(_TAGS)
            parts.append(f"<{tag}>{_random_markup(rng, depth + 1)}</{tag}>")
        else:
            parts.append("".join(rng.choices(_PIECES, k=rng.randint(1, 12))))
    return "".join(parts)


@pytest.mark.timeout(30)
def test_split_message_random_markup_splits_within_the_limit_and_loses_no_text():
    for seed in range(1500):
        rng = random.Random(seed)
        markup, limit = _random_markup(rng), rng.randint(10, 120)
        chunks = split_message(markup, limit=limit)
        assert all(_utf16_len(chunk) <= limit and _is_balanced(chunk) for chunk in chunks), (seed, limit, chunks)
        assert "".join(_text_of(chunk) for chunk in chunks) == _text_of(markup), (seed, limit)
