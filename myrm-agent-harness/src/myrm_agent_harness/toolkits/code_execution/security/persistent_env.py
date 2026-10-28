"""Environment variables a command leaves set in the persistent shell.

A bash session outlives its commands, so a variable exported by one command is still set for every later one,
including commands judged read-only. ``export BASH_ENV=./x`` or ``export GIT_EXTERNAL_DIFF=./x`` therefore makes a
later ``git diff`` or ``bash -c`` run the script. Setting the variable for one command only (``NAME=value cmd``)
does not outlive that command and is judged by the risk classifier instead.

[INPUT]
- blacklist::is_code_injection_env_name (POS: The environment variables that make a program run what the value names)
- core.security.shell_command_lexer::shell_words, split_command_spans (POS: Quote-aware command splitting)

[OUTPUT]
- persistent_env_injection: The injection variable a command exports, or None.

[POS]
Layer 2 (BLOCK) check of ``shell_command_analyzer``. It reads the shell words, so quoting (``export "NAME=x"``),
several names in one ``export``, ``declare -x``/``typeset -x`` and ``readonly`` are seen as well as the plain form.
A name that is only known at run time (``export "$NAME=x"``) cannot be judged here; the sandbox, not this check, is
what contains a command that builds one.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.shell_command_lexer import shell_words, split_command_spans
from myrm_agent_harness.toolkits.code_execution.security.blacklist import is_code_injection_env_name

# ``builtin`` and ``command`` only hand the next word to the shell, so ``command export X`` exports as well.
_PASSTHROUGH = frozenset({"builtin", "command"})
_ALWAYS_PERSISTENT = frozenset({"export", "readonly"})
_EXPORT_ONLY_WITH_FLAG = frozenset({"declare", "typeset"})


def persistent_env_injection(command: str) -> str | None:
    """The code-injection variable that ``command`` exports into its shell, or None."""
    for start, end in split_command_spans(command):
        words = shell_words(command[start:end])
        if not words:
            continue
        while words[0] in _PASSTHROUGH and len(words) > 1:
            words = words[1:]
        builtin, args = words[0], words[1:]
        if builtin in _EXPORT_ONLY_WITH_FLAG and not any(_exports(arg) for arg in args):
            continue
        if builtin not in _ALWAYS_PERSISTENT | _EXPORT_ONLY_WITH_FLAG:
            continue
        for arg in args:
            name = arg.split("=", 1)[0].rstrip("+")
            if is_code_injection_env_name(name):
                return name
    return None


def _exports(flags: str) -> bool:
    """Whether a ``declare``/``typeset`` option word carries the export flag (``-x``, ``-gx``, ``-rx``)."""
    return flags.startswith("-") and not flags.startswith("--") and "x" in flags
