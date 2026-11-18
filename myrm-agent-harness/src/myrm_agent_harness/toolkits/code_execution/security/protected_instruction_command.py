"""Which protected instruction file a shell command line writes.

A write is a redirect into the file, ``sed -i``, ``tee``, ``cp``, ``mv``, ``rm`` or ``truncate`` naming it, the same
operations as PowerShell cmdlets or cmd commands (``Set-Content``, ``Remove-Item``, ``copy``, ``del``), or an
interpreter (``python``, ``node``, ``ruby``, ``perl``) that opens it for writing. The names are the protected-path
rules the file tools enforce, and a backslash between path segments separates them as it does there (a backslash
before a space escapes the space): ``AGENTS.md.bak`` is another file for both. A line the read-only classifier judges
SAFE writes nothing, so a search that only spells an edit command (``grep -n rm AGENTS.md``) is not a write.

The line is read command by command, so a read beside an unrelated command (``rm -rf build && cat AGENTS.md``) is not a
write. The reading is lexical: it does not tell the file a command copies from apart from the one it copies to, it
reads the text of a quoted argument as it reads the command around it, a search that spells an edit command is still
taken for a write when the line is not read-only as a whole (it redirects, groups with parentheses, or holds a write),
a cmd command counts only as the first word of a command (``if exist AGENTS.md del AGENTS.md`` is not read), and it
does not reach a file through a symlink, a glob, a variable or one of the other names Windows gives it (a trailing
dot, an 8.3 short name). A command continued onto the next line, or holding a quoted argument that spans lines, is one
command. The time to read a line grows with its length, not with the square of it.

[INPUT]
- core.security.path.rules::PROTECTED_INSTRUCTION_PATTERNS (POS: Protected-path policy)
- core.security.shell_command_lexer::split_command_spans (POS: Shared lexical layer of the shell command security checks: where each command of a line starts and ends)
- toolkits.code_execution.security.risk_classifier::classify_command_risk (POS: Command risk classifier for approval auto-allow decisions.)

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
from myrm_agent_harness.toolkits.code_execution.security.risk_classifier import CommandRiskLevel, classify_command_risk


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
# The rule names spell their separators with ``/``, so a backslash between path segments becomes one; a backslash before
# whitespace escapes it and stays. Replacing a character by one character keeps every index of the line, so the spans of
# the original line cut the normalised text as well.
_PATH_SEPARATOR: Final = re.compile(r"\\(?=\S)")

# A redirect target is one word: a quoted word may hold spaces, and so may an unquoted one that escapes them.
_REDIRECT: Final = re.compile(
    rf">&?\s*(?:\"(?:[^\"]*?/)??|'(?:[^']*?/)??|(?:(?:\\\s|[^\s;|'\"<>])*?/)??){_FILE}",
    re.IGNORECASE,
)
# A command that writes, replaces, moves, deletes or empties the file named among its arguments: the POSIX tools, and
# the PowerShell cmdlets that do the same (nothing else is spelled like them, so they count wherever they stand).
_EDIT_COMMAND: Final = re.compile(
    r"\b(?:tee|cp|mv|rm|truncate|(?:Set|Add|Clear)-Content|Out-File|(?:Remove|Copy|Move|Rename|New)-Item)\b",
    re.IGNORECASE,
)
# The cmd commands PowerShell also accepts are everyday words, so only the first word of a command counts, not a word
# among the arguments of another command (``git commit -m 'move AGENTS.md notes'``). That is the command itself, which
# ``cmd /c`` or ``powershell -Command`` in front hands on whatever options it carries, and the word after a separator or
# an opening bracket: where the commands of a quoted payload (``cmd /c "cd repo && del AGENTS.md"``) or of a ``{ }``
# block start. An option takes a value only when it is one of the words ``-ExecutionPolicy`` and ``-WindowStyle`` take,
# so the command word that follows ``/c`` is never read as a value.
_CMD_COMMAND: Final = r"(?:del|erase|copy|move|ren|rename)(?![\w.-])"
_OPTION_VALUE: Final = (
    r"(?:Bypass|Unrestricted|RemoteSigned|AllSigned|Restricted|Undefined|Default|Hidden|Normal|Minimized|Maximized)"
)
_SHELL_OPTIONS: Final = rf"(?:[/-]\w+\s+(?:{_OPTION_VALUE}\s+)?)*"
_COMMAND_START_VERB: Final = re.compile(
    rf"\s*(?:(?:cmd|powershell|pwsh)(?:\.exe)?\s+{_SHELL_OPTIONS}['\"]?)?{_CMD_COMMAND}", re.IGNORECASE
)
_GROUPED_VERB: Final = re.compile(rf"[;&|({{]\s*{_CMD_COMMAND}", re.IGNORECASE)
# ``sed`` edits in place with ``-i`` (also inside a cluster such as ``-ni``) or ``--in-place``, wherever the flag stands
# among its arguments. Two searches that each start where the last ended keep a long run of flag letters linear.
_SED: Final = re.compile(r"(?<![\w-])sed(?=\s)", re.IGNORECASE)
_IN_PLACE: Final = re.compile(r"\s(?:-[a-zA-Z]*i|--in-place)", re.IGNORECASE)
# A name among the arguments starts after a space, a path separator, a quote or a comma that lists paths, and ends
# where a word does: at one of those, a redirect, or the parenthesis or backtick that closes a group or a substitution
# around the command.
_ARGUMENT_NAME: Final = re.compile(rf"[\s/'\",](?P<name>{_NAMES})(?:[\s/'\"<>),`]|$)", re.IGNORECASE)
# An interpreter that opens the file for writing.
_INTERPRETER: Final = re.compile(r"(?:python[0-9.]*|node|ruby|perl)\b", re.IGNORECASE)
_OPENS_FOR_WRITE: Final = re.compile(r"write|open", re.IGNORECASE)
_FILE_NAME: Final = re.compile(_FILE, re.IGNORECASE)


def _edit_arguments_start(span: str) -> int | None:
    """Where the arguments of the first edit command of one command begin; the file it edits is named among them."""
    edit_commands = (_EDIT_COMMAND.search(span), _COMMAND_START_VERB.match(span), _GROUPED_VERB.search(span))
    starts = [match.end() for match in edit_commands if match]
    if (sed := _SED.search(span)) and _IN_PLACE.search(span, sed.end()):
        starts.append(sed.end())
    return min(starts, default=None)


def _written_name(span: str) -> str | None:
    """The protected name one command of a line writes.

    Each form looks for its first keyword only: a name that follows a later keyword follows the first one too, and
    that keeps the reading linear in the length of a command that repeats the keywords.
    """
    if match := _REDIRECT.search(span):
        return match.group("name")
    if (start := _edit_arguments_start(span)) is not None and (argument := _ARGUMENT_NAME.search(span, start)):
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
    text = _PATH_SEPARATOR.sub("/", command)
    if not _ANY_NAME.search(text) or classify_command_risk(command) is CommandRiskLevel.SAFE:
        return None
    for start, end in split_command_spans(command):
        if (name := _written_name(text[start:end])) is not None:
            return name
    return None
