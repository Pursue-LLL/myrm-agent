"""Shell Command Readings — the texts the shell command rule tables are matched against.

A rule written for one command has to fire wherever the shell runs it, so a command line is judged in more than one
reading, the line as written first:

- every command line the line hands to a shell, read with the shell's own quoting: the script of ``sh -c`` / ``eval``
  and a ``trap`` handler wherever the interpreter stands in a command (``then sh -c '...'``, ``docker exec ctr sh -c
  '...'``), and the body of a ``$(...)`` or backtick substitution, however they are quoted;
- each command of the line and of those scripts apart, also without the closer of a grouping glued to its end
  (``(cd d && echo x > uv.lock)``), so a pattern that ends at its command is not hidden by what the line puts behind it.

A command behind ``sudo``, ``env`` or ``timeout`` is judged where it stands: the rules match a command wherever it
stands in the text, and the quoted text of its arguments stays masked.

The work is bounded. Each reading is expanded once, and the readings beside the line itself add up to at most
``MAX_COMMAND_READINGS`` texts and ``MAX_READING_CHARS`` characters. The scripts and substitutions come first, since
what a line hides inside quotes stands in no other reading: when they do not fit, ``CommandReadings.complete`` is
False and the caller refuses the line, because a payload may sit in what was not read. The commands apart only restate
text the readings above already hold, so they fill what is left of the bounds, those of a script before those of the
line itself; a line that runs past them (a long script written through a heredoc) is judged on what was found.

[INPUT]
- core.security.shell_command_lexer::read_commands, split_command_spans (POS: Shared lexical layer of the shell command security checks)
- core.security.shell_wrapper_peel::MAX_COMMAND_READINGS, SHELLS, shell_script, substitution_bodies (POS: Shared reading of shell prefixes, the single home of the transparent-wrapper table)

[OUTPUT]
- MAX_READING_CHARS: The most characters the readings beside the line itself may add up to.
- UNREAD_SCRIPTS_EVIDENCE: The bounds a line that nests too many scripts ran into, as the threat evidence words them.
- CommandReadings: The texts to judge for a command line, and whether every script it hands to a shell is among them.
- command_readings: The readings of a command line, the line as written first.

[POS]
Shell Command Readings — the texts the shell command rule tables are matched against.
"""

from __future__ import annotations

import re
from typing import Final, NamedTuple

from myrm_agent_harness.core.security.shell_command_lexer import read_commands, split_command_spans
from myrm_agent_harness.core.security.shell_wrapper_peel import (
    MAX_COMMAND_READINGS,
    SHELLS,
    shell_script,
    substitution_bodies,
)

# Every reading is matched against the whole rule catalogue, so a line that nests the same long script hundreds of
# times (``eval eval eval ...``) costs readings x length; the budget keeps that to a fraction of a second, far above
# what a real line nests.
MAX_READING_CHARS: Final = 256 * 1024

UNREAD_SCRIPTS_EVIDENCE: Final = (
    f"more than {MAX_COMMAND_READINGS} readings or {MAX_READING_CHARS // 1024} KB of scripts"
)


class CommandReadings(NamedTuple):
    """The texts to judge for a command line, and whether every script it hands to a shell is among them."""

    texts: tuple[str, ...]
    complete: bool


def _statements(text: str) -> list[str]:
    """Each command of *text* apart (``a;b && c`` is three)."""
    return [text[start:end] for start, end in split_command_spans(text)]


# A ``(`` that opens a group: at the start of a command, or after a blank, a separator, another ``(`` or ``!``. One
# glued to a word is a substitution (``$(``, ``<(``) or part of a script's own text (``print(x)``).
_GROUP_OPENER: Final = re.compile(r"(?:^|[\s;&|({!])\(")


def _without_closers(statement: str) -> str:
    """*statement* without the ``)`` of a group glued to its end: ``echo x > uv.lock)`` of ``(cd d && ...)``.

    A rule whose pattern ends at its command or file name (``(?:\\s|$)``) does not see through a ``)`` stuck to it.
    A group opens in this statement or an earlier one, so a trailing ``)`` is read as a group closer when the
    statement holds a group opener or more ``)`` than ``(``. The ``)`` of ``print(x)`` or ``$(...)`` closes nothing
    the line puts behind it, and reading those statements twice would double the work on every line of a script.
    """
    stripped = statement.rstrip(") \t")
    if stripped == statement:
        return statement
    closes_group = statement.count(")") > statement.count("(") or _GROUP_OPENER.search(statement) is not None
    return stripped if closes_group else statement


def _embedded_scripts(statement: str) -> tuple[str, ...]:
    """The scripts a shell, ``eval`` or ``trap`` anywhere in *statement* is given (``trap 'cleanup' EXIT``).

    A script is run whatever stands in front of its interpreter: a prefix (``sudo``, ``env``, ``timeout``), a
    reserved word (``then sh -c '...'``), a redirection, ``docker exec ctr`` or ``ssh host``, a ``case`` arm. So each
    word that names an interpreter is tried, in the words of each command as ``read_commands`` resolves them:
    quotes removed, grouping parentheses and reserved words left out. ``eval`` joins every word after it into its
    script, so only the first ``eval`` of a command is read here; a later one is inside that script and is read
    with it.
    """
    scripts: list[str] = []
    for command in read_commands(statement):
        words = command.words
        eval_read = False
        for index, word in enumerate(words):
            base = word.rsplit("/", 1)[-1]
            script: str | None = None
            if base == "trap" and index + 2 < len(words) and not words[index + 1].startswith("-"):
                script = words[index + 1]
            elif base in SHELLS or (base == "eval" and not eval_read):
                eval_read = eval_read or base == "eval"
                script = shell_script(words, index)
            if script is not None:
                scripts.append(script.strip())
    return tuple(scripts)


def _handed_to_a_shell(statement: str) -> list[str]:
    """The command lines *statement* hands to a shell: its scripts and the bodies of its substitutions.

    The statement is read as written and without the closer of a grouping glued to its end, which is how the
    commands of the line are judged apart.
    """
    found: list[str] = []
    for source in dict.fromkeys((statement, _without_closers(statement))):
        found.extend(_embedded_scripts(source))
        found.extend(body.strip() for body in substitution_bodies(source))
    return [text for text in found if text]


def command_readings(command: str) -> CommandReadings:
    """The texts to judge for *command*, the line as written first, then what it hands to a shell, then each command.

    The scripts are found first, in every command of the line and, one nesting level at a time, of each script. A
    script that no longer fits the bounds leaves ``complete`` False. The commands of the line and of its scripts
    apart come last and fill what the scripts left of the bounds; past them only the texts found so far are judged.
    """
    root = command.strip()
    readings: dict[str, None] = {root: None}
    room = MAX_READING_CHARS
    pending = [root]
    parsed: list[list[str]] = []
    while pending:
        statements = _statements(pending.pop())
        parsed.append(statements)
        for statement in statements:
            for script in _handed_to_a_shell(statement):
                if script in readings:
                    continue
                room -= len(script)
                if len(readings) >= MAX_COMMAND_READINGS or room < 0:
                    return CommandReadings(tuple(readings), complete=False)
                readings[script] = None
                pending.append(script)
    for statements in reversed(parsed):
        for statement in statements:
            for text in (statement, _without_closers(statement)):
                if not text or text in readings:
                    continue
                room -= len(text)
                if len(readings) >= MAX_COMMAND_READINGS or room < 0:
                    return CommandReadings(tuple(readings), complete=True)
                readings[text] = None
    return CommandReadings(tuple(readings), complete=True)
