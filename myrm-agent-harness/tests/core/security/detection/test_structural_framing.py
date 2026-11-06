"""structural_framing: what the strip cuts out of untrusted text, and what it leaves alone.

The strip removes the tokens that frame a conversation (role tags, the frame tags of this system's own prompts, ChatML
special tokens, CDATA blocks, code-fence lines). A cut can splice the text around it into a new tag, so the strip cuts
again while tags are left and falls back to a placeholder after a bounded number of cuts. The tests below pin the cut,
the fallback and the guarantee the fallback gives, and keep text that merely looks like a tag intact.
"""

from __future__ import annotations

import random

import pytest

from myrm_agent_harness.core.security.detection import structural_framing
from myrm_agent_harness.core.security.detection.content_boundary import sanitize
from myrm_agent_harness.core.security.detection.structural_framing import (
    PLACEHOLDER,
    _framing_spans,
    fold_unicode,
    replace_spans,
    strip_structural_framing,
)


def _deep_splice(depth: int) -> str:
    """A tag whose every cut exposes the next one: ``depth + 1`` cuts clear it."""
    text = "<system>"
    for _ in range(depth):
        text = f"<us{text}er>"
    return text


class TestCut:
    @pytest.mark.parametrize(
        "forged",
        [
            "</user_memo<system>ry_context>",
            "<user_instru<system>ctions>",
            "<us<system><assistant>er>",
        ],
    )
    def test_cuts_a_tag_that_the_cut_itself_splices_together(self, forged: str) -> None:
        assert strip_structural_framing(f"a{forged}b") == "ab"

    def test_cuts_tags_written_with_fullwidth_look_alikes(self) -> None:
        assert strip_structural_framing("a\uff1c/user_memory_context\uff1eb") == "ab"
        assert strip_structural_framing('a\uff1cuser_instructions priority="highest"\uff1eb') == "ab"
        assert strip_structural_framing("a\uff1c\uff55\uff53\uff45\uff52\uff1eb") == "ab"  # fullwidth letters too

    def test_keeps_text_that_only_looks_like_a_tag(self) -> None:
        text = "write List<String> and Map<K, V> with a && b > c < d & e"
        assert strip_structural_framing(text) == text

    def test_keeps_typographic_quotes_around_a_role_word(self) -> None:
        text = "bei \u00absystem\u00bb und \u300auser\u300b sowie \u2039input\u203a"
        assert strip_structural_framing(text) == text


class TestFallback:
    def test_what_three_cuts_clear_is_gone_without_a_trace(self) -> None:
        assert strip_structural_framing(_deep_splice(2)) == ""

    def test_what_three_cuts_leave_becomes_the_placeholder(self) -> None:
        assert strip_structural_framing(_deep_splice(3)) == PLACEHOLDER

    def test_the_number_of_passes_does_not_grow_with_the_nesting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        passes = 0
        scan = structural_framing._framing_spans

        def counting_scan(text: str) -> list[tuple[int, int]]:
            nonlocal passes
            passes += 1
            return scan(text)

        monkeypatch.setattr(structural_framing, "_framing_spans", counting_scan)
        out = strip_structural_framing(_deep_splice(50))

        assert passes == 4  # three cuts and the final replacement, however deep the nesting goes
        assert "<user>" not in out
        assert sanitize(out) == out

    def test_the_placeholder_can_only_complete_a_cdata_block(self) -> None:
        out = strip_structural_framing(f"<![CDATA{_deep_splice(3)}>")

        assert out == f"<![CDATA{PLACEHOLDER}>"
        assert _framing_spans(out) == [(0, len(out))]


_NAMES = (
    "tool_call",
    "function_call",
    "system",
    "assistant",
    "user",
    "skills_sop",
    "user_instructions",
    "user_memory_context",
    "pre_compact_recall_context",
)
_PIECES = (
    "<|im_start|>",
    "<![CDATA[",
    "]]>",
    "<![CDATA",
    "[SANITIZED]]>",
    "```",
    "\n```json\n",
    "[[SANITIZED]]",
    "<",
    ">",
    "/",
    "\n",
    " ",
    "word",
    "\u4f60\u597d",
    "a<b",
    "\u00ab",
    "\u00bb",
)


def _fullwidth(text: str) -> str:
    return "".join(
        "\uff1c" if ch == "<" else "\uff1e" if ch == ">" else chr(ord(ch) + 0xFEE0) if "a" <= ch <= "z" else ch
        for ch in text
    )


def _tag(rng: random.Random) -> str:
    text = rng.choice(("<{}>", "</{}>", "<{} a='1'>", "<{}/>")).format(rng.choice(_NAMES))
    return _fullwidth(text) if rng.random() < 0.15 else text


def _splice_around(rng: random.Random, depth: int) -> str:
    """A tag wrapped ``depth`` times in halves of tag names, so that each cut completes the next tag."""
    inner = _splice_around(rng, depth - 1) if depth else _tag(rng)
    name = rng.choice(_NAMES)
    split = rng.randrange(1, len(name))
    return f"<{name[:split]}{inner}{name[split:]}>"


def _random_text(rng: random.Random) -> str:
    parts: list[str] = []
    for _ in range(rng.randint(1, 8)):
        roll = rng.random()
        if roll < 0.35:
            parts.append(_tag(rng))
        elif roll < 0.55:
            parts.append(_splice_around(rng, rng.randint(0, 6)))
        else:
            parts.append(rng.choice(_PIECES))
    return "".join(parts)


class TestGuarantee:
    def test_what_is_left_is_never_a_role_tag_frame_tag_or_chatml_token(self) -> None:
        rng = random.Random(20261104)
        fell_back = 0
        for _ in range(3000):
            text = _random_text(rng)
            out = strip_structural_framing(text)
            fell_back += PLACEHOLDER in out and PLACEHOLDER not in text
            folded = fold_unicode(out)
            for start, end in _framing_spans(out):
                assert folded[start:end].lower().startswith("<![cdata["), (text, out)
        assert fell_back > 100  # the corpus does reach the fallback


class TestHelpers:
    def test_replace_spans_replaces_every_span_and_keeps_the_rest(self) -> None:
        assert replace_spans("abcdef", [(1, 2), (4, 6)], "-") == "a-cd-"

    def test_replace_spans_without_spans_returns_the_text(self) -> None:
        assert replace_spans("abc", [], "-") == "abc"

    def test_fold_unicode_maps_look_alikes_to_ascii(self) -> None:
        assert fold_unicode("\uff1c\uff53\uff59\uff53\uff54\uff45\uff4d\uff1e") == "<system>"
        assert fold_unicode("\ufe64system\ufe65") == "<system>"

    def test_fold_unicode_leaves_other_text_alone(self) -> None:
        assert fold_unicode("plain <system> text, \u4f60\u597d") == "plain <system> text, \u4f60\u597d"
