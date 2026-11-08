"""Whether a bash command is a plain call of one skill's script, and of which skill.

The settings a user saved for a skill (the mailbox password of ``imap-smtp-email``) are meant for the skill's own
script. A command that merely contains ``.claude/skills/<name>/`` somewhere (in a comment, as an ``echo`` operand,
next to ``env``) is not that script, so the name found by text search is not enough to hand the settings over.
A plain call is a command line whose every command is exactly ``[interpreter] .claude/skills/<name>/<file> args``:
no pipe or chain to another program, no expansion that builds words at run time, no subshell.

[INPUT]
- core.security.shell_command_lexer::strip_comments, split_command_spans, shell_words, has_word_expansion, iter_syntax_chars (POS: the one reading of a shell command line)

[OUTPUT]
- plain_skill_call: the skill a command line is a plain call of, or None
- skill_call_notice: the calling convention the skill loader shows the model
- settings_withheld_note: the reason a failed command did not get the skill's saved settings

[POS]
Identity check of a skill call, shared by the bash executor (who receives the skill's settings) and the texts that
tell the model how to call a skill script, so the rule it is told is the rule that is applied.
"""

from __future__ import annotations

import re
from typing import Final

from myrm_agent_harness.core.security.shell_command_lexer import (
    has_word_expansion,
    iter_syntax_chars,
    shell_words,
    split_command_spans,
    strip_comments,
)

_SKILL_FILE: Final = re.compile(r"(?:\./)?\.claude/skills/([^/\s]+)/(.+)")
_INTERPRETERS: Final = frozenset({"python", "python3", "bash", "sh", "node"})
# Interpreter flags that take no value, so the script is still the next word.
_BARE_FLAGS: Final = frozenset({"-u", "-B", "-E", "-I", "-O", "-OO", "-q", "-s", "-S"})
_REDIRECT: Final = re.compile(r"(?:\d*|&)[<>]")
_REDIRECT_OPERATOR: Final = re.compile(r"(?:\d*|&)(?:>{1,2}|<)")


def plain_skill_call(command: str) -> str | None:
    """The skill *command* is a plain call of, or None.

    Every command of the line must call a file of the same skill; one that does not (a second program, a
    ``cd``, a shell function, an unparseable fragment) makes the whole line not plain.
    """
    text = strip_comments(command)
    skills: set[str] = set()
    for start, end in split_command_spans(text):
        skill = _skill_of_command(text[start:end])
        if skill is None:
            return None
        skills.add(skill)
    return skills.pop() if len(skills) == 1 else None


def _skill_of_command(command: str) -> str | None:
    """The skill one command calls, or None when it is anything else."""
    # A parenthesis is a subshell or a process substitution; either runs a command the words do not show.
    if has_word_expansion(command) or any(char in "()" for _, char in iter_syntax_chars(command)):
        return None
    words = shell_words(command)
    if not words:
        return None
    operands = _without_redirections(words)
    index = 0
    if operands and operands[0] in _INTERPRETERS:
        index = 1
        while index < len(operands) and operands[index] in _BARE_FLAGS:
            index += 1
    return _skill_of_file(operands[index]) if index < len(operands) else None


def _without_redirections(words: list[str]) -> list[str]:
    """The words that are not a redirection; a bare ``>`` or ``<`` also takes the word after it."""
    operands: list[str] = []
    skip_target = False
    for word in words:
        if skip_target:
            skip_target = False
        elif _REDIRECT.match(word):
            skip_target = _REDIRECT_OPERATOR.fullmatch(word) is not None
        else:
            operands.append(word)
    return operands


def _skill_of_file(path: str) -> str | None:
    """The skill a ``.claude/skills/<name>/<file>`` path names, or None for another path or one that climbs out."""
    match = _SKILL_FILE.fullmatch(path)
    if match is None:
        return None
    name, file_path = match.groups()
    parts = file_path.split("/")
    if name in {".", ".."} or ".." in parts or not parts[-1]:
        return None
    return name


def skill_call_notice(skill: str) -> str:
    """The calling convention of a skill's scripts, as the quoted block the skill loader puts under the title."""
    return (
        f"> **Script calls**: call a script by its full path, as one plain command: "
        f"`{_example_call(skill)}`. A shortened path such as `scripts/xxx.py` is not recognised as a call of this skill.\n"
        f"> **Saved settings**: the settings you saved for this skill reach only a command made of such calls. "
        f"Anything else in it (a pipe to another program, `cd`, `$VAR`, `$(...)`) withholds them, so run that step as "
        f"a separate command.\n"
        f"> **Skill files**: all files of this skill are under `.claude/skills/{skill}/`.\n\n"
    )


def settings_withheld_note(skill: str) -> str:
    """Why the failed command of *skill* ran without the skill's saved settings, and what to run instead."""
    return (
        f"The saved settings of skill `{skill}` were not passed to this command: they go only to a plain call of "
        f"one of the skill's own files, from files that are exactly as shipped. Run the script alone, as "
        f"`{_example_call(skill)}`."
    )


def _example_call(skill: str) -> str:
    return f"python3 .claude/skills/{skill}/scripts/xxx.py ARGS"
