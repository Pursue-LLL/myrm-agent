"""Tests for ``read_commands``: the commands of a shell line and their words, from the program that runs."""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.shell_command_lexer import read_commands


def command_words(text: str) -> list[list[str]]:
    """The words of every command of *text*, from the program that runs."""
    return [list(command.words) for command in read_commands(text)]


class TestReadCommands:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("git push origin main", [["git", "push", "origin", "main"]]),
            ("git push;echo done", [["git", "push"], ["echo", "done"]]),
            ("a&&b||c|d&e;f", [["a"], ["b"], ["c"], ["d"], ["e"], ["f"]]),
            ("git status\n\ngit log", [["git", "status"], ["git", "log"]]),
            ("# note\nls", [["ls"]]),
            ("ls # git push", [["ls"]]),
            ("echo 'a; git push'", [["echo", "a; git push"]]),
            ('git commit -m "fix git push"', [["git", "commit", "-m", "fix git push"]]),
            ("\\rm -rf x", [["rm", "-rf", "x"]]),
            ('"rm" -rf x', [["rm", "-rf", "x"]]),
            ("", []),
            ("  ;  ", []),
        ],
    )
    def test_each_command_is_its_own_words(self, text: str, expected: list[list[str]]) -> None:
        assert command_words(text) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("if true; then git push; fi", [["true"], ["git", "push"], ["fi"]]),
            ("for f in a; do rm $f; done", [["for", "f", "in", "a"], ["rm", "$f"], ["done"]]),
            ("while read l; do echo $l; done", [["read", "l"], ["echo", "$l"], ["done"]]),
            ("! rm x", [["rm", "x"]]),
            ("time make", [["make"]]),
            ("{ rm x; }", [["rm", "x"], ["}"]]),
            ("then", []),
            ("if then do", []),
        ],
    )
    def test_the_words_start_at_the_program_that_runs(self, text: str, expected: list[list[str]]) -> None:
        assert command_words(text) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("(git push)", [["git", "push"]]),
            ("( git push )", [["git", "push"]]),
            ("(cd d;git push)", [["cd", "d"], ["git", "push"]]),
            ("(cd d && git push) || true", [["cd", "d"], ["git", "push"], ["true"]]),
            ("((rm x))", [["rm", "x"]]),
            ('echo "(a)"', [["echo", "(a)"]]),
        ],
    )
    def test_the_parentheses_of_a_subshell_are_no_part_of_a_word(self, text: str, expected: list[list[str]]) -> None:
        assert command_words(text) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("f() { rm x; }", [["rm", "x"], ["}"]]),
            ("f () { rm x; }", [["rm", "x"], ["}"]]),
            ("function f { rm x; }", [["rm", "x"], ["}"]]),
            ("function f() { rm x; }", [["rm", "x"], ["}"]]),
            ("f() ( rm x )", [["rm", "x"]]),
            ("f() { git push; }; f", [["git", "push"], ["}"], ["f"]]),
        ],
    )
    def test_the_head_of_a_function_definition_is_no_part_of_the_words(
        self, text: str, expected: list[list[str]]
    ) -> None:
        assert command_words(text) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("case $x in a) rm x;; esac", [["rm", "x"], ["esac"]]),
            ("case $x in (a) rm x;; esac", [["rm", "x"], ["esac"]]),
            ("case $x in a) echo 1;; b) git push;; esac", [["echo", "1"], ["git", "push"], ["esac"]]),
            ("case $x in a|b) rm x;; esac", [["rm", "x"], ["esac"]]),
            ("case $x in\n  a) rm x ;;\n  *) git push ;;\nesac", [["rm", "x"], ["git", "push"], ["esac"]]),
            ("case $x in a) ;; esac", [["esac"]]),
            ("case $x in", []),
            ("case", []),
        ],
    )
    def test_the_label_of_a_case_arm_is_no_part_of_the_words(self, text: str, expected: list[list[str]]) -> None:
        assert command_words(text) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("grep -e 'a)' notes", [["grep", "-e", "a)", "notes"]]),
            ("echo case in a) f", [["echo", "case", "in", "a)", "f"]]),
            ("git log --grep case", [["git", "log", "--grep", "case"]]),
            ("echo function f", [["echo", "function", "f"]]),
        ],
    )
    def test_those_words_stay_when_a_program_stands_before_them(self, text: str, expected: list[list[str]]) -> None:
        assert command_words(text) == expected

    def test_the_text_is_the_command_as_written(self) -> None:
        assert [command.text for command in read_commands('echo a;  "rm" -rf "x y" ; (ls)')] == [
            "echo a",
            '"rm" -rf "x y"',
            "(ls)",
        ]

    def test_text_with_an_open_quote_is_still_read_at_its_blanks(self) -> None:
        assert command_words("git push 'origin") == [["git", "push", "'origin"]]

    def test_a_quote_left_open_hides_no_command_behind_it(self) -> None:
        found = read_commands("python deploy.py <<EOF\nit's\nEOF\nrm -rf x")

        assert [list(command.words) for command in found] == [
            ["python", "deploy.py", "<<EOF"],
            ["it's"],
            ["EOF"],
            ["rm", "-rf", "x"],
        ]
        assert found[-1].text == "rm -rf x"

    def test_the_reading_of_a_line_is_shared_and_cannot_be_changed_by_a_reader(self) -> None:
        first = read_commands("git push; echo done")

        assert read_commands("git push; echo done") is first
        assert isinstance(first, tuple)
        assert all(isinstance(command.words, tuple) for command in first)
