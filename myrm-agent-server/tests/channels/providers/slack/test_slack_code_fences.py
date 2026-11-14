"""Slack code blocks: fences read the CommonMark way, and a block that documents blocks stays one Slack block.

Slack ends a code block at any run of three backticks. A block fenced by four or more is written as a three-backtick
block, and the runs of backticks inside it (the blocks it documents) are broken with a zero-width space, so none of
them ends it early and its code is not turned into prose.
"""

from __future__ import annotations

import random

import pytest

from app.channels.providers.slack.format_converter import md_to_slack_mrkdwn
from app.channels.rendering.renderer import render
from app.channels.types import OutboundMessage, RenderStyle

ZWS = "\u200b"


def _defang(line: str) -> str:
    """Independent reading of the rule: a zero-width space after every second backtick of each run of three or more."""
    pieces: list[str] = []
    index = 0
    while index < len(line):
        if line[index] != "`":
            pieces.append(line[index])
            index += 1
            continue
        end = index
        while end < len(line) and line[end] == "`":
            end += 1
        run = end - index
        pieces.append(ZWS.join("`" * min(2, run - done) for done in range(0, run, 2)) if run >= 3 else "`" * run)
        index = end
    return "".join(pieces)


class TestBlocksFencedByMoreThanThreeBackticks:
    def test_a_block_that_documents_a_block_is_one_slack_block_with_its_code_untouched(self) -> None:
        text = 'Intro **bold**\n````markdown\n```python\nprint("a")  # **x** <y>\n```\ntext **not bold**\n````\nAfter **bold**'

        expected = [
            "Intro *bold*",
            "```markdown",
            f"``{ZWS}`python",
            'print("a")  # **x** <y>',
            f"``{ZWS}`",
            "text **not bold**",
            "```",
            "After *bold*",
        ]

        assert md_to_slack_mrkdwn(text).split("\n") == expected

    def test_a_longer_run_inside_is_broken_until_no_three_backticks_are_left(self) -> None:
        fence = "`" * 10
        text = f"{fence}\n````\n`````````\n{fence}"

        result = md_to_slack_mrkdwn(text).split("\n")

        assert result[0] == result[-1] == "```"
        assert all("```" not in line for line in result[1:-1])
        assert [line.replace(ZWS, "") for line in result[1:-1]] == ["````", "`````````"]

    def test_a_shorter_bare_fence_inside_does_not_close_the_block_and_the_same_length_does(self) -> None:
        text = "````\n```\ncode **x**\n````\n**after**"

        assert md_to_slack_mrkdwn(text) == f"```\n``{ZWS}`\ncode **x**\n```\n*after*"

    def test_a_fence_line_with_an_info_string_inside_a_block_is_code(self) -> None:
        text = "```\n``` python\n**x**\n```\n**y**"

        assert md_to_slack_mrkdwn(text) == f"```\n``{ZWS}` python\n**x**\n```\n*y*"

    def test_a_run_of_backticks_in_the_middle_of_a_code_line_cannot_end_the_block(self) -> None:
        assert md_to_slack_mrkdwn("```\nuse ``` here\n```") == f"```\nuse ``{ZWS}` here\n```"

    def test_the_indentation_and_info_string_of_a_fence_line_stay(self) -> None:
        assert md_to_slack_mrkdwn("  ````js title=a\ncode\n  ````") == "  ```js title=a\ncode\n  ```"

    def test_a_block_with_no_closing_fence_runs_to_the_end_untouched(self) -> None:
        assert md_to_slack_mrkdwn("````\nfoo **x**\nbar <y>") == "```\nfoo **x**\nbar <y>"


class TestWhatIsNotABlock:
    def test_three_backticks_around_code_on_one_line_do_not_open_a_block(self) -> None:
        assert md_to_slack_mrkdwn("```x = 1``` then **bold**\nnext **line**") == "```x = 1``` then *bold*\nnext *line*"

    def test_tildes_are_text_for_slack_has_no_block_fenced_by_them(self) -> None:
        assert md_to_slack_mrkdwn("~~~\n**x**\n~~~") == "~~~\n*x*\n~~~"


class TestRandomDocuments:
    _PROSE = {"plain **bold** text": "plain *bold* text", "a <b> & c": "a &lt;b&gt; &amp; c", "no markup": "no markup"}

    @staticmethod
    def _block(rng: random.Random, closed: bool) -> tuple[list[str], list[str]]:
        length = rng.randint(3, 6)
        info = rng.choice(["", "py", "c++"])
        # Bare runs shorter than the opener and fence lines with an info string do not close a block: they are code.
        content_lines = ["x = **1** <z>", "a ``` b", "```py", "plain", *("`" * run for run in range(3, length))]
        content = [rng.choice(content_lines) for _ in range(rng.randint(0, 5))]
        source = ["`" * length + info, *content, *(["`" * length] if closed else [])]
        expected = [f"```{info}", *(_defang(line) for line in content), *(["```"] if closed else [])]
        return source, expected

    def test_blocks_of_any_fence_length_survive_whole_among_prose(self) -> None:
        for seed in range(1500):
            rng = random.Random(seed)
            source: list[str] = []
            expected: list[str] = []
            for _ in range(rng.randint(1, 6)):
                if rng.random() < 0.5:
                    line = rng.choice(sorted(self._PROSE))
                    source.append(line)
                    expected.append(self._PROSE[line])
                    continue
                closed = rng.random() < 0.8
                block_source, block_expected = self._block(rng, closed)
                source.extend(block_source)
                expected.extend(block_expected)
                if not closed:
                    break  # a block with no closing fence runs to the end of the document
            assert md_to_slack_mrkdwn("\n".join(source)) == "\n".join(expected), f"seed {seed}: {source!r}"


class TestSplitReply:
    @pytest.mark.parametrize("limit", [200, 400, 900])
    def test_every_chunk_of_a_long_nested_block_is_balanced_in_slack_terms(self, limit: int) -> None:
        inner = "".join(f"```python\nvalue_{index} = {index}  # **keep** <this>\n```\n" for index in range(60))
        reply = OutboundMessage(
            channel="slack",
            recipient_id="u1",
            content=f"Here is the template:\n\n````markdown\n{inner}````\n\nThat was it.",
            user_id="u1",
        )

        chunks = render(reply, RenderStyle(format="mrkdwn", max_text_length=limit))

        assert len(chunks) > 3
        for chunk in chunks:
            lines = chunk.split("\n")
            fence_lines = [line for line in lines if line.startswith("```")]
            assert len(fence_lines) % 2 == 0, chunk
            assert all("```" not in line for line in lines if not line.startswith("```")), chunk
        assert "".join(chunks).count("**keep** <this>") == 60
