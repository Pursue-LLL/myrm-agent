"""Environment variable names that make a program run what their value names.

[INPUT]
- (standard library only)

[OUTPUT]
- CODE_INJECTION_ENV_VARS: The exact names (dynamic linker, language runtimes, shell startup, git program hooks).
- CODE_INJECTION_ENV_PREFIXES: The name families that steer the dynamic loader (``LD_*``, ``DYLD_*``).
- is_code_injection_env_name: Whether a name is one of them, case-insensitively.

[POS]
The one definition of "this variable makes a later program run foreign code". Every place that must refuse such a
name reads it from here: the persistent-shell export check, the child-process and MCP environment blacklists
(``DANGEROUS_ENV_VARS`` is built from it) and the names a person may stage as a one-command credential. Proxies, TLS
and package-source names are not part of it: they redirect traffic, and a person may legitimately set them.
"""

from __future__ import annotations

# Names that make a later program run what their value names. Setting one in a shell that outlives the command
# turns every following command, including ones judged read-only, into a way to run it.
_LINKER_INJECTION_ENV_VARS: frozenset[str] = frozenset(
    {
        # Dynamic linker injection (Linux)
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "LD_AUDIT",
        # Dynamic linker injection (macOS)
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "DYLD_FRAMEWORK_PATH",
    }
)

_RUNTIME_INJECTION_ENV_VARS: frozenset[str] = frozenset(
    {
        # Runtime hijacking / module injection
        "NODE_OPTIONS",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PERL5OPT",
        "RUBYOPT",
    }
)

_SHELL_STARTUP_ENV_VARS: frozenset[str] = frozenset(
    {
        # A script every non-interactive bash sources before it runs
        "BASH_ENV",
    }
)

_GIT_PROGRAM_ENV_VARS: frozenset[str] = frozenset(
    {
        # Git command hijacking — arbitrary code execution via git hooks/editors
        "GIT_SSH_COMMAND",
        "GIT_SSH",
        "GIT_PROXY_COMMAND",
        "GIT_ASKPASS",
        "GIT_EDITOR",
        "GIT_SEQUENCE_EDITOR",
        "GIT_EXTERNAL_DIFF",
        "GIT_EXEC_PATH",
        "GIT_TEMPLATE_DIR",
    }
)

CODE_INJECTION_ENV_VARS: frozenset[str] = (
    _LINKER_INJECTION_ENV_VARS | _RUNTIME_INJECTION_ENV_VARS | _SHELL_STARTUP_ENV_VARS | _GIT_PROGRAM_ENV_VARS
)

# Whole families of the same kind: every ``LD_*`` and ``DYLD_*`` variable steers the dynamic loader.
CODE_INJECTION_ENV_PREFIXES: tuple[str, ...] = ("LD_", "DYLD_")


def is_code_injection_env_name(name: str) -> bool:
    """Whether a variable of this name makes a later program run what its value names (case-insensitive)."""
    upper = name.upper()
    return upper in CODE_INJECTION_ENV_VARS or upper.startswith(CODE_INJECTION_ENV_PREFIXES)
