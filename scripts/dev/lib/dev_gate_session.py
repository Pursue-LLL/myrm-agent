"""Domain model for one Chrome E2E session owned by the Dev Gate coordinator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class ExecutionMode(StrEnum):
    SHARED = "SHARED"
    PRIVATE = "PRIVATE"


class AccessScope(StrEnum):
    READ = "READ"
    NAMESPACE_WRITE = "NAMESPACE_WRITE"
    GLOBAL_WRITE = "GLOBAL_WRITE"


class Workload(StrEnum):
    STANDARD = "STANDARD"
    LIVE = "LIVE"
    DESKTOP = "DESKTOP"


class SessionState(StrEnum):
    SUBMITTED = "SUBMITTED"
    PRIVATE_ADMIT = "PRIVATE_ADMIT"
    PREPARING = "PREPARING"
    PAGE_OPEN = "PAGE_OPEN"
    BODY = "BODY"
    TEARDOWN = "TEARDOWN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = frozenset(
    {SessionState.SUCCEEDED, SessionState.FAILED, SessionState.CANCELLED}
)


class TerminalConflictError(ValueError):
    """Raised when finish would contradict an existing terminal session state."""


_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.SUBMITTED: frozenset(
        {SessionState.PRIVATE_ADMIT, SessionState.PREPARING, SessionState.CANCELLED}
    ),
    SessionState.PRIVATE_ADMIT: frozenset(
        {SessionState.PREPARING, SessionState.FAILED, SessionState.CANCELLED}
    ),
    SessionState.PREPARING: frozenset(
        {SessionState.PAGE_OPEN, SessionState.FAILED, SessionState.CANCELLED}
    ),
    SessionState.PAGE_OPEN: frozenset(
        {SessionState.BODY, SessionState.FAILED, SessionState.CANCELLED}
    ),
    SessionState.BODY: frozenset(
        {SessionState.TEARDOWN, SessionState.FAILED, SessionState.CANCELLED}
    ),
    SessionState.TEARDOWN: frozenset(TERMINAL_STATES),
    SessionState.SUCCEEDED: frozenset(),
    SessionState.FAILED: frozenset(),
    SessionState.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    execution_mode: ExecutionMode
    access_scope: AccessScope
    workload: Workload
    namespace: str = ""
    priority: int = 0
    private_credits: int = 1

    def validate(self) -> None:
        if (
            self.execution_mode is ExecutionMode.SHARED
            and self.access_scope is AccessScope.GLOBAL_WRITE
        ):
            raise ValueError("SHARED+GLOBAL_WRITE is forbidden")
        if (
            self.access_scope is AccessScope.NAMESPACE_WRITE
            and not self.namespace.strip()
        ):
            raise ValueError("NAMESPACE_WRITE requires a namespace")
        if self.private_credits < 1:
            raise ValueError("private_credits must be positive")


@dataclass(frozen=True, slots=True)
class SessionOwnership:
    browser_context_id: str = ""
    page_ids: tuple[str, ...] = ()
    lease_id: str = ""
    runtime_id: str = ""


@dataclass(frozen=True, slots=True)
class CleanupReceipt:
    closed_page_ids: tuple[str, ...] = ()
    closed_context_id: str = ""
    released_lease_id: str = ""
    released_runtime_id: str = ""
    ledger_cleaned: bool = False
    physical_released: bool | None = None
    sealed: bool = False
    requested_at: float = 0.0
    observed_at: float = 0.0
    completed_at: float = 0.0


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_id: str
    owner_pid: int
    owner_token: str
    owner_process_start: str
    owner_boot_id: str
    test_node_id: str
    policy: SessionPolicy
    state: SessionState
    version: int
    submitted_at: float
    phase_started_at: float
    last_progress_at: float
    hard_deadline: float
    node_started_at: float = 0.0
    current_node: str = ""
    ownership: SessionOwnership = field(default_factory=SessionOwnership)
    outcome: str = ""
    failure_token: str = ""
    cleanup: CleanupReceipt = field(default_factory=CleanupReceipt)

    def to_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "state": self.state.value,
            "policy": {
                **asdict(self.policy),
                "execution_mode": self.policy.execution_mode.value,
                "access_scope": self.policy.access_scope.value,
                "workload": self.policy.workload.value,
            },
        }


def assert_transition(current: SessionState, target: SessionState) -> None:
    if target not in _TRANSITIONS[current]:
        raise ValueError(f"invalid session transition: {current.value}->{target.value}")


def initial_state(policy: SessionPolicy) -> SessionState:
    policy.validate()
    if policy.execution_mode is ExecutionMode.PRIVATE:
        return SessionState.PRIVATE_ADMIT
    return SessionState.PREPARING
