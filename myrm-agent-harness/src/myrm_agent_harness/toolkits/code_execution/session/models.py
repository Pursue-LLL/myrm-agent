"""Value types of a persistent shell session.

[INPUT]
- (none)

[OUTPUT]
SessionState: Lifecycle states enum.
SessionExecutionResult: Frozen dataclass for command execution results.
SessionConfig: Configuration dataclass for session parameters.
CommandEnv: Environment applied around one command (sticky settings, scoped credentials).

[POS]
Plain data shared by the session base, its command stream and the executors; no behaviour, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, auto


class SessionState(Enum):
    """Lifecycle states of a persistent session."""

    IDLE = auto()
    STARTING = auto()
    ACTIVE = auto()
    RECOVERING = auto()
    CLOSING = auto()
    TERMINATED = auto()


@dataclass(frozen=True)
class SessionExecutionResult:
    """Result of a command execution in a persistent session."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    error: str | None = None
    duration: float = 0.0
    is_armored: bool = False


@dataclass(frozen=True)
class CommandEnv:
    """Environment applied around one command of a shell that outlives it.

    ``sticky`` values (a skill's settings) are exported before every command and stay for the later ones.
    ``scoped`` values (credentials) are exported before the command and unset right after it, so the shell holds no
    credential between commands and a later command is not handed what an earlier one was granted. All commands of a
    conversation share the shell: this limits what is delivered, it does not contain a command that tampers with the
    shell itself (a ``trap``, a function) and so observes what later commands are granted.
    """

    sticky: Mapping[str, str] = field(default_factory=dict)
    scoped: Mapping[str, str] = field(default_factory=dict)


@dataclass
class SessionConfig:
    """Configuration for a persistent session."""

    session_id: str
    work_dir: str
    timeout: int = 60
    env: dict[str, str] = field(default_factory=dict)
    sandbox_mode: str = "auto"
    max_memory_mb: int = 2048
    readonly_workspace: bool = False
    allow_network: bool = True
