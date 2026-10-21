"""Tests for universal text_utils.extract_safe_regions()."""

from __future__ import annotations

import re

from app.channels.rendering.text_utils import extract_safe_regions


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
