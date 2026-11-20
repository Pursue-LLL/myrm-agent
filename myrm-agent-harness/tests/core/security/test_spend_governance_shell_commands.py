"""Spend governance reads a shell line command by command.

The irreversible-action gate and the script target of an approval look at the words of a command, so the word that
ends one command (``push;``, ``publish&&``) must not be taken for part of a longer word, and the words of one command
must not be read as the sub-command of another.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.core.security.spend_governance import extract_script_file_target, is_irreversible_social_action

_IRREVERSIBLE_COMMANDS = [
    "git push",
    "git -C dir push origin main",
    "git --no-pager push --force",
    "npm publish --access public",
    "pnpm --filter pkg publish",
    "yarn publish",
    "twine upload dist/*",
    "docker push img:1",
    "podman push img:1",
    "gh release create v1",
    "gh pr merge 42 --squash",
    "gh pr create --fill",
]

_LINES = [
    "{c}",
    "echo a && {c}",
    "{c} && echo done",
    "{c} || true",
    "{c} | tee log",
    "{c} &",
    "echo a ; {c}",
    "{c} ; echo done",
    "{c};",
    "{c};echo done",
    "echo a;{c}",
    "{c}&&echo done",
    "{c}||true",
    "{c}|cat",
    "{c}&",
    "a\n{c}",
    "if true; then {c}; fi",
    "for i in 1 2; do {c}; done",
    "({c})",
    "({c});echo done",
    "(cd d;{c})",
    "(cd d && {c})",
    "(cd d; {c}) && echo done",
    "sudo {c}",
    "env A=1 {c}",
]


@pytest.mark.parametrize("command", _IRREVERSIBLE_COMMANDS)
@pytest.mark.parametrize("line", _LINES)
def test_an_irreversible_command_is_found_whatever_joins_it_to_the_line(line: str, command: str) -> None:
    assert is_irreversible_social_action("bash", {"command": line.format(c=command)}) is True


@pytest.mark.parametrize(
    "line",
    [
        "git status; echo push",
        "git status;echo push",
        "git status && echo push",
        "git log\necho push",
        "npm install;echo publish",
        "docker build .;echo push",
        "gh pr view 42;echo merge",
        "git commit -m 'a; b' && git status",
        'echo "git push"',
        'echo "(git push)"',
        "echo 'npm publish'",
        "(cd d && git status)",
        'git commit -m "fix: git push retries"',
        "git commit -m 'docs: how npm publish works' && git log",
        "git status # then git push",
    ],
)
def test_the_words_of_one_command_are_not_the_sub_command_of_another(line: str) -> None:
    assert is_irreversible_social_action("bash", {"command": line}) is False


def test_a_script_named_before_a_separator_is_the_script_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "deploy.py"
    script.write_text("print('deploy')\n")
    runner = tmp_path / "run.sh"
    runner.write_text("echo run\n")
    monkeypatch.chdir(tmp_path)
    expected = str(script.resolve())

    for command in (
        "python deploy.py",
        "python deploy.py && echo done",
        "python deploy.py; echo done",
        "python deploy.py;echo done",
        "python deploy.py|tee log",
        "python deploy.py&",
        "(python deploy.py)",
    ):
        assert extract_script_file_target("bash", {"command": command}) == expected, command

    spaced = tmp_path / "my deploy.py"
    spaced.write_text("print('deploy')\n")
    assert extract_script_file_target("bash", {"command": 'python "my deploy.py"; echo done'}) == str(spaced.resolve())

    assert extract_script_file_target("bash", {"command": "./run.sh;echo done"}) == str(runner.resolve())
    assert extract_script_file_target("bash", {"command": "echo deploy.py; python -V"}) is None
