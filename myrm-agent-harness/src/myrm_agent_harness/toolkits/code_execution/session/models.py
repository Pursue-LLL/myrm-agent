"""Value types of a persistent shell session.

[INPUT]
- (none)

[OUTPUT]
SessionState: Lifecycle states enum.
SessionExecutionResult: Frozen dataclass for command execution results.
SessionConfig: Configuration dataclass for session parameters.

[POS]
Plain data shared by the session base, its command stream and the executors; no behaviour, no I/O.
"""

from __future__ import annotations

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


@dataclass
class SessionConfig:
    """Configuration for a persistent session."""

    session_id: str
    work_dir: str
    timeout: int = 60
    env: dict[str, str] = field(default_factory=dict)
    sandbox_mode: str = "auto"
    max_memory_mb: int = 2048
