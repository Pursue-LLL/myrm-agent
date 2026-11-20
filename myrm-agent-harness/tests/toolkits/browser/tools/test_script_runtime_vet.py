"""What a script passes before it reaches the interpreter: what is refused, and that nothing is rewritten."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.browser.tools.script_runtime import ScriptRejectedError, vet_script


class TestWhatIsRefusedBeforeAnythingRuns:
    @pytest.mark.parametrize(
        ("script", "line"),
        [
            pytest.param("x = 1\ndef foo(:", 2, id="syntax-error"),
            pytest.param('x = 1\ny = """abc', 2, id="unterminated-string"),
            pytest.param("x = 1\ny = (\n  1,", 2, id="unclosed-bracket"),
            pytest.param("  x = 1\ny = 2", 1, id="indented-first-line"),
        ],
    )
    def test_a_syntax_error_is_rejected_with_the_line_of_the_script(self, script: str, line: int) -> None:
        with pytest.raises(ScriptRejectedError, match=rf"^SyntaxError in script: .* \(line {line}\)$"):
            vet_script(script)

    @pytest.mark.parametrize("script", ["import os", "from os import path", "x = 1\nif x:\n    import json"])
    def test_imports_are_refused_before_anything_runs(self, script: str) -> None:
        with pytest.raises(ScriptRejectedError, match=r"^\[Error\] Imports are unavailable in scripts \(line \d\)\.$"):
            vet_script(script)

    @pytest.mark.parametrize(
        "script",
        [
            pytest.param("print('\ud800')", id="lone-surrogate"),
            pytest.param("x = " + " + ".join(["1"] * 100_000), id="expression-nested-too-deeply"),
        ],
    )
    def test_text_the_parser_cannot_take_is_rejected_instead_of_escaping(self, script: str) -> None:
        with pytest.raises(ScriptRejectedError, match=r"^\[Error\] The script cannot be parsed: "):
            vet_script(script)


class TestWhatReachesTheInterpreter:
    @pytest.mark.parametrize(
        "script",
        [
            pytest.param('x = """a\n  b\nc"""', id="triple-quoted"),
            pytest.param('v = 1\nx = f"{\nv=}"', id="f-string-debug-field-across-lines"),
            pytest.param("if True:\n\tx = '''a\n\t  b'''", id="tab-indented"),
            pytest.param('x = "a\u2028b"', id="unicode-line-separator"),
            pytest.param('x = "a\x0cb"', id="form-feed"),
            pytest.param("if True:\n  \x0c  x = 1", id="form-feed-inside-indentation"),
        ],
    )
    def test_a_script_that_passes_the_checks_reaches_the_interpreter_as_written(self, script: str) -> None:
        assert vet_script(script) == script

    def test_every_newline_style_becomes_the_line_feed_the_compiler_reads(self) -> None:
        assert vet_script("x = '''a\r\nb\rc'''\r\ny = 1") == "x = '''a\nb\nc'''\ny = 1"
