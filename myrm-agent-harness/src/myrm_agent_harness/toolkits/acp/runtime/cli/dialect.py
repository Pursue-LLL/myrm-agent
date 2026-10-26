"""Per-CLI dialects — how each CLI resumes a conversation and limits its own turns.

The CLIs share the NDJSON event vocabulary (``parser``) but not their command lines: Claude resumes with a
``--resume <id>`` flag, Codex with an ``exec resume <id>`` subcommand, and only Claude has a native turn limit.
Keeping those differences in one place leaves the runtime free of per-CLI branching.

[INPUT]
- toolkits.acp.auth._profiles::profile_for (POS: Authentication profile registry; resolves a command to its backend)

[OUTPUT]
- CliDialect: command-line differences of one CLI (resume, native turn limit, partial-message streaming)
- dialect_for: the dialect of a command, or None for a CLI without a known one
- has_native_turn_limit: whether a command's CLI stops itself at the configured turn limit
- is_session_id: whether a string has the shape of a CLI session id

[POS]
Per-CLI launch knowledge of CliRuntime. A CLI without a dialect is spawned as configured, without resume or limits.
"""

from __future__ import annotations

import re

from myrm_agent_harness.toolkits.acp.auth._profiles import profile_for

# Claude and Codex both identify a conversation by a canonical hyphenated UUID. A resume id comes from a store
# the CLI did not write, and Codex starts a brand-new thread (instead of failing) on a malformed one, so an id
# that does not look like one is never replayed.
_SESSION_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def is_session_id(value: str) -> bool:
    """Whether ``value`` has the shape of a CLI-native session id."""
    return _SESSION_ID.fullmatch(value) is not None


class CliDialect:
    """The command-line behavior of one CLI; the base class is a CLI that can neither resume nor limit turns."""

    name = ""
    max_turns_flag: str | None = None
    partial_messages_flag: str | None = None

    def is_resuming(self, args: list[str]) -> bool:
        """Whether the configured args already pick the conversation themselves."""
        return False

    def with_resume(self, args: list[str], cli_session_id: str) -> list[str] | None:
        """``args`` continuing ``cli_session_id``, or None when the id or the args cannot carry a resume."""
        return self._resume(args, cli_session_id) if is_session_id(cli_session_id) else None

    def with_max_turns(self, args: list[str], limit: int) -> list[str]:
        """``args`` with the CLI's own turn limit, unchanged for a CLI that has none."""
        if self.max_turns_flag is None or limit <= 0 or self.max_turns_flag in args:
            return args
        return [*args, self.max_turns_flag, str(limit)]

    def with_partial_messages(self, args: list[str]) -> list[str]:
        """``args`` asking for text as it is written, when the CLI can and the output is stream-json."""
        flag = self.partial_messages_flag
        if flag is None or flag in args or "stream-json" not in args:
            return args
        return [*args, flag]

    def _resume(self, args: list[str], cli_session_id: str) -> list[str] | None:
        return None


class _ClaudeDialect(CliDialect):
    name = "claude"
    max_turns_flag = "--max-turns"
    partial_messages_flag = "--include-partial-messages"

    def is_resuming(self, args: list[str]) -> bool:
        return "--resume" in args

    def _resume(self, args: list[str], cli_session_id: str) -> list[str] | None:
        return [*args, "--resume", cli_session_id]


class _CodexDialect(CliDialect):
    name = "codex"

    def is_resuming(self, args: list[str]) -> bool:
        return "exec" in args and "resume" in args[args.index("exec") + 1 :]

    def _resume(self, args: list[str], cli_session_id: str) -> list[str] | None:
        """``codex ... exec <opts>`` becomes ``codex ... exec resume <opts> <id>``; the prompt follows the id."""
        if "exec" not in args:
            return None
        exec_index = args.index("exec")
        return [*args[: exec_index + 1], "resume", *args[exec_index + 1 :], cli_session_id]


_DIALECTS: dict[str, CliDialect] = {"claude": _ClaudeDialect(), "codex": _CodexDialect()}


def dialect_for(command: str | None) -> CliDialect | None:
    """The dialect of ``command`` (resolved like its auth profile), or None for a CLI without one."""
    profile = profile_for(command) if command else None
    return _DIALECTS.get(profile.backend) if profile is not None else None


def has_native_turn_limit(command: str | None) -> bool:
    """Whether the CLI stops itself at the configured turn limit, so a caller has no need to count turns for it."""
    dialect = dialect_for(command)
    return dialect is not None and dialect.max_turns_flag is not None
