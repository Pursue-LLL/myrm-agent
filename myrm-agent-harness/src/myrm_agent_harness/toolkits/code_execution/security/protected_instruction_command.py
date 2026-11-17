"""Which protected instruction file a shell command line writes.

A write is a redirect into the file, ``sed -i``, ``tee``, ``cp``, ``mv``, ``rm`` or ``truncate`` naming it, or an
interpreter (``python``, ``node``, ``ruby``, ``perl``) that opens it for writing. The names are the protected-path
rules the file tools enforce, so the shell tools and the file tools protect the same files: ``AGENTS.md.bak`` is
another file for both.

The line is read command by command, so a read beside an unrelated command (``rm -rf build && cat AGENTS.md``) is not a
write. The reading is lexical: it does not tell the file a command copies from apart from the one it copies to, and it
reads the text of a quoted argument as it reads the command around it. A command continued onto the next line, or
holding a quoted argument that spans lines, is one command. The time to read a line grows with its length, not
with the square of it.

[INPUT]
- core.security.path.rules::PROTECTED_INSTRUCTION_PATTERNS (POS: Protected-path policy)
- core.security.shell_command_lexer::split_command_spans (POS: Shared lexical layer of the shell command security checks: where each command of a line starts and ends)

[OUTPUT]
- protected_instruction_mutation_target: The protected name a command line writes, or None.

[POS]
The shell-side reading of the protected instruction files. The threat analyzer, the permission engine and the
allow-always guard all ask this one function, so they cannot disagree about which command lines write one of them.
"""

from __future__ import annotations

import re
from typing import Final

from myrm_agent_harness.core.security.path.rules import PROTECTED_INSTRUCTION_PATTERNS
from myrm_agent_harness.core.security.shell_command_lexer import split_command_spans


def _protected_names() -> str:
    """The protected names as one regex alternation.

    A rule ``**/name`` protects the file itself and ``**/dir/**`` everything under a protected directory, so a
    directory rule contributes its prefix: the alternation matches the directory as well as its contents.
    """
    return "|".join(re.escape(rule.removeprefix("**/").removesuffix("/**")) for rule in PROTECTED_INSTRUCTION_PATTERNS)


_NAMES: Final = _protected_names()
# A protected name that does not go on into a longer file name: ``AGENTS.md.bak`` is another file, as for the file tools.
_FILE: Final = rf"(?P<name>{_NAMES})(?![\w.~-])"
# Every write form needs one of the names, so a line without any of them is not a write.
_ANY_NAME: Final = re.compile(_NAMES, re.IGNORECASE)

_REDIRECT: Final = re.compile(rf">\s*['\"]?(?:[^\s;|'\"<>]*?/)??{_FILE}", re.IGNORECASE)
# A command that edits in place, writes, replaces, moves, deletes or empties the file named among its arguments.
_EDIT_COMMAND: Final = re.compile(r"\b(?:sed\s+-[a-zA-Z]*i[a-zA-Z]*|tee|cp|mv|rm|truncate)\b", re.IGNORECASE)
_ARGUMENT_NAME: Final = re.compile(rf"[\s/'\"](?P<name>{_NAMES})(?:[\s/'\"<>]|$)", re.IGNORECASE)
# An interpreter that opens the file for writing.
_INTERPRETER: Final = re.compile(r"(?:python[0-9.]*|node|ruby|perl)\b", re.IGNORECASE)
_OPENS_FOR_WRITE: Final = re.compile(r"write|open", re.IGNORECASE)
_FILE_NAME: Final = re.compile(_FILE, re.IGNORECASE)


def _written_name(span: str) -> str | None:
    """The protected name one command of a line writes.

    Each form looks for its first keyword only: a name that follows a later keyword follows the first one too, and
    that keeps the reading linear in the length of a command that repeats the keywords.
    """
    if match := _REDIRECT.search(span):
        return match.group("name")
    if (command := _EDIT_COMMAND.search(span)) and (argument := _ARGUMENT_NAME.search(span, command.end())):
        return argument.group("name")
    if (
        (interpreter := _INTERPRETER.search(span))
        and (opener := _OPENS_FOR_WRITE.search(span, interpreter.end()))
        and (file := _FILE_NAME.search(span, opener.end()))
    ):
        return file.group("name")
    return None


def protected_instruction_mutation_target(command: str) -> str | None:
    """The protected name, as the protected-path rules spell it, that a command line writes; None when none does."""
    if not _ANY_NAME.search(command):
        return None
    for start, end in split_command_spans(command):
        if (name := _written_name(command[start:end])) is not None:
            return name
    return None
