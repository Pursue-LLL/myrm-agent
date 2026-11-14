"""Unit tests for fuzzy_replace and the boundary conditions of fuzzy_match.

Covers:
  - replace_all support
  - Multi-match rejection (safety)
  - A match the content does not hold verbatim is not a success
  - Edge cases (empty input, single line, no match)
"""

from __future__ import annotations

from myrm_agent_harness.utils.fuzzy_match import (
    FuzzyMatchResult,
    FuzzyReplaceResult,
    fuzzy_find,
    fuzzy_replace,
)

# ===================================================================
# 1. fuzzy_replace
# ===================================================================


class TestFuzzyReplace:
    """Replace operations with fuzzy matching."""

    def test_exact_replace(self) -> None:
        result = fuzzy_replace("hello world", "hello", "goodbye")
        assert result.success
        assert result.content == "goodbye world"
        assert result.strategy == "exact"

    def test_fuzzy_replace_with_trim(self) -> None:
        content = "  def foo():  \n    pass  "
        result = fuzzy_replace(content, "def foo():\npass", "def bar():\npass")
        assert result.success
        assert "bar" in result.content

    def test_no_match_returns_original(self) -> None:
        result = fuzzy_replace("hello", "goodbye", "hi")
        assert not result.success
        assert result.content == "hello"

    def test_multi_match_rejected(self) -> None:
        content = "foo bar foo"
        result = fuzzy_replace(content, "foo", "baz")
        assert not result.success

    def test_replace_all(self) -> None:
        content = "foo bar foo"
        result = fuzzy_replace(content, "foo", "baz", replace_all=True)
        assert result.success
        assert result.content == "baz bar baz"

    def test_empty_fragment(self) -> None:
        result = fuzzy_replace("hello", "", "world")
        assert not result.success

    def test_preserves_surrounding(self) -> None:
        content = "before\nhello world\nafter"
        result = fuzzy_replace(content, "hello world", "goodbye world")
        assert result.success
        assert result.content == "before\ngoodbye world\nafter"

    def test_unicode_in_content_replace(self) -> None:
        """Replace should work when content has Unicode smart quotes."""
        content = "print(\u201chello\u201d)"
        result = fuzzy_replace(content, 'print("hello")', 'print("world")')
        assert result.success
        assert result.content == "print(\u201cworld\u201d)" or "world" in result.content

    def test_unicode_in_fragment_replace(self) -> None:
        """Replace should work when fragment has Unicode smart quotes."""
        content = 'print("hello")'
        result = fuzzy_replace(content, "print(\u201chello\u201d)", 'print("world")')
        assert result.success
        assert result.content == 'print("world")'

    def test_unicode_replace_preserves_original(self) -> None:
        """After Unicode-matched replace, non-matched content stays original."""
        content = "x = \u201ca\u201d\ny = \u201cb\u201d"
        result = fuzzy_replace(content, 'x = "a"', 'x = "z"')
        assert result.success
        assert "\u201cb\u201d" in result.content

    def test_a_match_the_content_does_not_hold_verbatim_is_not_a_success(self) -> None:
        """The line strategies rejoin the lines they match with ``\\n``; content that separates its lines with
        anything else does not hold that text, and replacing nothing must not read as a success."""
        for separator in ("\r", "\r\n", "\x0c", "\u2028"):
            content = f"def a():{separator}    return 1{separator}def b():"
            result = fuzzy_replace(content, "def a():\n    return 1", "def a():\n    return 10")
            assert not result.success, repr(separator)
            assert result.content == content


# ===================================================================
# 2. Edge cases
# ===================================================================


class TestEdgeCases:
    """Boundary conditions and safety checks."""

    def test_single_line_content(self) -> None:
        result = fuzzy_find("x = 1", "x = 1")
        assert result is not None

    def test_very_long_content(self) -> None:
        content = "\n".join(f"line_{i}" for i in range(1000))
        result = fuzzy_find(content, "line_500\nline_501")
        assert result is not None
        assert result.strategy == "exact"

    def test_unicode_in_content_not_fragment(self) -> None:
        """Unicode in content but not fragment should still work."""
        content = "print(\u201chello\u201d)"
        fragment = 'print("hello")'
        result = fuzzy_find(content, fragment)
        assert result is not None

    def test_result_types(self) -> None:
        result = fuzzy_find("hello", "hello")
        assert isinstance(result, FuzzyMatchResult)

        replace_result = fuzzy_replace("hello", "hello", "world")
        assert isinstance(replace_result, FuzzyReplaceResult)

    def test_escape_normalized_no_match(self) -> None:
        """Escape normalized converts but still doesn't match content."""
        content = "line1_XYZXYZ"
        fragment = "line1\\nline2"
        result = fuzzy_find(content, fragment)
        assert result is None or result.strategy != "escape_normalized"

    def test_block_anchored_empty_inner(self) -> None:
        """Block anchored with exactly 3 lines and no inner content."""
        content = "start\n\nend"
        fragment = "start\n\nend"
        result = fuzzy_find(content, fragment)
        assert result is not None

    def test_context_aware_trailing_empty_lines(self) -> None:
        """Fragment with trailing empty lines gets trimmed before matching."""
        content = "class A:\n    x = 1\n    y = 2\n    end"
        fragment = "class A:\n    x = 1\n    y = 2\n    end\n\n"
        result = fuzzy_find(content, fragment)
        assert result is not None

    def test_unicode_recovery_failure(self) -> None:
        """When Unicode content can't be mapped back, strategy is skipped."""
        content = "\u201ctest\u201d"
        fragment = '"test"'
        result = fuzzy_find(content, fragment)
        assert result is not None
