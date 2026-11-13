"""Tests for the code-aware helpers of universal text_utils: extract_safe_regions(), with_protected_code_blocks()."""

from __future__ import annotations

import random
import re
import time

from app.channels.rendering.text_utils import extract_safe_regions, with_protected_code_blocks


class TestExtractSafeRegions:
    """Test code-block-aware pattern extraction."""

    def test_basic_no_code_blocks(self) -> None:
        """Basic extraction when no code blocks present."""
        text = "Hi @alice, meet @bob"
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 2
        assert [m.group() for m in matches] == ["@alice", "@bob"]
        assert [m.group(1) for m in matches] == ["alice", "bob"]

    def test_exclude_fenced_code_block(self) -> None:
        """Mentions inside fenced code blocks should be excluded."""
        text = "Hi @alice, check:\n```python\n@bob in code\n```"
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 1
        assert matches[0].group() == "@alice"

    def test_exclude_inline_code(self) -> None:
        """Mentions inside inline code should be excluded."""
        text = "Hi @alice, see `@bob in code`"
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 1
        assert matches[0].group() == "@alice"

    def test_mixed_code_blocks(self) -> None:
        """Both fenced and inline code blocks should be excluded."""
        text = "Hi @alice, `@bob`, and:\n```\n@charlie\n```\nTalk to @dave"
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 2
        assert [m.group() for m in matches] == ["@alice", "@dave"]

    def test_boundary_mention_at_code_edge(self) -> None:
        """Mentions at code block boundaries."""
        text = "@alice ```@bob``` @charlie"
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 2
        assert [m.group() for m in matches] == ["@alice", "@charlie"]

    def test_multiline_fenced_code_block(self) -> None:
        """Multiline fenced code block."""
        text = """Hi @alice:
```
Line 1 @bob
Line 2 @charlie
```
Talk to @dave"""
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 2
        assert [m.group() for m in matches] == ["@alice", "@dave"]

    def test_nested_inline_in_fenced(self) -> None:
        """Inline code inside fenced code block (both excluded)."""
        text = "Hi @alice\n```\n`@bob` in code\n```"
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 1
        assert matches[0].group() == "@alice"

    def test_empty_pattern(self) -> None:
        """Empty pattern should return no matches."""
        text = "Hi @alice"
        matches = extract_safe_regions(text, r"@$")
        assert len(matches) == 0

    def test_empty_text(self) -> None:
        """Empty text should return no matches."""
        text = ""
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 0

    def test_regex_capture_groups(self) -> None:
        """Capture groups should work correctly."""
        text = "Hi @alice:server.com and @bob:example.org"
        matches = extract_safe_regions(text, r"@(\w+):(\S+)")
        assert len(matches) == 2
        assert matches[0].group(1) == "alice"
        assert matches[0].group(2) == "server.com"
        assert matches[1].group(1) == "bob"

    def test_consecutive_code_blocks(self) -> None:
        """Multiple consecutive code blocks."""
        text = "@alice `@bob` `@charlie` @dave"
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 2
        assert [m.group() for m in matches] == ["@alice", "@dave"]

    def test_multiple_matches_in_safe_region(self) -> None:
        """Multiple matches in same safe region."""
        text = "Hi @alice @bob @charlie, check `@dave`"
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 3
        assert [m.group() for m in matches] == ["@alice", "@bob", "@charlie"]

    def test_exclude_fenced_code_false(self) -> None:
        """exclude_fenced_code=False should include fenced code matches."""
        text = "Hi @alice\n```\n@bob\n```"
        matches = extract_safe_regions(text, r"@(\w+)", exclude_fenced_code=False)
        assert len(matches) == 2
        assert [m.group() for m in matches] == ["@alice", "@bob"]

    def test_exclude_inline_code_false(self) -> None:
        """exclude_inline_code=False should include inline code matches."""
        text = "Hi @alice `@bob`"
        matches = extract_safe_regions(text, r"@(\w+)", exclude_inline_code=False)
        assert len(matches) == 2
        assert [m.group() for m in matches] == ["@alice", "@bob"]

    def test_no_matches_anywhere(self) -> None:
        """No pattern matches in text."""
        text = "Hi alice, meet bob"
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 0

    def test_compiled_pattern(self) -> None:
        """Should accept compiled Pattern objects."""
        text = "Hi @alice, meet @bob"
        pattern = re.compile(r"@(\w+)")
        matches = extract_safe_regions(text, pattern)
        assert len(matches) == 2
        assert [m.group() for m in matches] == ["@alice", "@bob"]

    def test_complex_markdown(self) -> None:
        """Complex markdown with multiple elements."""
        text = """
# Title @alice
Hi **@bob**, check:
- `@charlie` in list
- @dave normal
```python
def func():
    # @eve comment
    pass
```
End @frank
"""
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 4
        assert [m.group() for m in matches] == ["@alice", "@bob", "@dave", "@frank"]

    def test_unicode_text(self) -> None:
        """Unicode characters in text."""
        text = "你好 @alice，见 `@bob`，@charlie"
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 2
        assert [m.group() for m in matches] == ["@alice", "@charlie"]

    def test_mention_at_text_boundaries(self) -> None:
        """Mentions at start and end of text."""
        text = "@alice middle @bob end @charlie"
        matches = extract_safe_regions(text, r"@(\w+)")
        assert len(matches) == 3
        assert [m.group() for m in matches] == ["@alice", "@bob", "@charlie"]

    def test_blocks_documented_by_a_longer_fence_are_excluded(self) -> None:
        """The three-backtick block inside a four-backtick block is code too, all the way through."""
        text = "Hi @alice:\n````markdown\n```bash\n@bob\n```\n@carol\n````\nTalk to @dave"
        matches = extract_safe_regions(text, r"@(\w+)")
        assert [m.group() for m in matches] == ["@alice", "@dave"]


class TestWithProtectedCodeBlocks:
    """The transform sees the text between code blocks and never the code."""

    @staticmethod
    def _shout(text: str) -> str:
        return text.upper()

    def test_code_is_untouched_and_the_rest_is_transformed(self) -> None:
        assert with_protected_code_blocks("a ```b``` c\n```\nd\n```\ne", self._shout) == "A ```b``` C\n```\nd\n```\nE"

    def test_a_digit_after_a_block_does_not_change_which_block_comes_back(self) -> None:
        assert with_protected_code_blocks("```a```1 ```b```2 x", self._shout) == "```a```1 ```b```2 X"

    def test_blocks_documented_by_a_longer_fence_stay_whole(self) -> None:
        text = "see\n````md\n```py\nprint(1)\n```\ntable | a\n````\nend"
        assert with_protected_code_blocks(text, self._shout) == "SEE\n````md\n```py\nprint(1)\n```\ntable | a\n````\nEND"

    def test_random_documents_transform_only_what_is_outside_code(self) -> None:
        for seed in range(1000):
            rng = random.Random(seed)
            pieces: list[tuple[str, str]] = []
            for _ in range(rng.randint(1, 8)):
                if rng.random() < 0.5:
                    word = rng.choice(("alpha", "beta", "gamma"))
                    pieces.append((word, word.upper()))
                else:
                    run = "`" * rng.randint(3, 10)
                    inner = "```\nin\n```\n" if len(run) > 3 else ""
                    code = f"{run}py\nx = 1\n{inner}{run}"
                    pieces.append((code, code))
            text = "\n\n".join(markdown for markdown, _ in pieces)
            expected = "\n\n".join(transformed for _, transformed in pieces)
            assert with_protected_code_blocks(text, self._shout) == expected, f"seed {seed}: {text!r}"

    def test_a_degenerate_line_of_backticks_is_handled_in_linear_time(self) -> None:
        # Tried at every offset against every length, a run of thousands of backticks takes seconds.
        degenerate = "`" * 8_000 + "a\n" + "x" * 8_000
        started = time.perf_counter()
        with_protected_code_blocks(degenerate, self._shout)
        extract_safe_regions(degenerate, r"x+")
        assert time.perf_counter() - started < 2.0
