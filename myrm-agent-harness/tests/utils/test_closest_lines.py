"""Unit tests for closest_lines — the "Did you mean?" hint of a text that was not found."""

from __future__ import annotations

from myrm_agent_harness.utils.closest_lines import find_closest_lines


class TestFindClosestLines:
    """find_closest_lines returns similar snippets when all strategies fail."""

    CONTENT = "def _process_data(config, *, validate=True):\n    if not validate:\n        return None\n    return config.get('data')"

    def test_similar_function_name(self) -> None:
        """Anchor line differs slightly — hint should find the real function."""
        hint = find_closest_lines("def process_data(config):", self.CONTENT)
        assert "Did you mean" in hint
        assert "_process_data" in hint

    def test_no_match_returns_empty(self) -> None:
        """Completely unrelated text → no hint."""
        hint = find_closest_lines("xyz", "abc\nmno\npqr")
        assert hint == ""

    def test_empty_inputs(self) -> None:
        assert find_closest_lines("", self.CONTENT) == ""
        assert find_closest_lines("def foo():", "") == ""

    def test_line_numbers_in_hint(self) -> None:
        """Hint should include line numbers for LLM reference."""
        hint = find_closest_lines("def process_data:", self.CONTENT)
        if hint:
            assert "|" in hint

    def test_max_results_respected(self) -> None:
        """Should not return more snippets than max_results."""
        content = "\n".join(f"def func_{i}(): pass" for i in range(20))
        hint = find_closest_lines("def func_5(): pass", content, max_results=2)
        assert hint.count("---") <= 1

    def test_all_blank_old_str(self) -> None:
        """old_str is all whitespace lines — no anchor found."""
        hint = find_closest_lines("   \n   \n  ", "def foo():\n    pass")
        assert hint == ""
