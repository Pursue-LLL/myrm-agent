"""Process-wide record of whether a person has taken control of the agent's browser or desktop.

[INPUT]
- asyncio / threading (POS: waiters are futures on the caller's loop, woken from any thread)
- langchain_core.tools::StructuredTool (POS: the tool coroutine the gate wraps)

[OUTPUT]
- UserControl: the single truth - `held`, `generation`, `acquire`, `release`, `wait_released`
- UserControlTimeoutError: the wait for the person outlasted its budget
- DEFAULT_WAIT_TIMEOUT_S: how long a tool waits for the person before refusing
- get_user_control: the process-wide instance every session defaults to
- UserControlSurface: what the gate needs from a session (the control it consults + the generation the model last observed)
- ToolRole: whether a tool call looks at the surface or changes it
- planned_against / plan_is_stale: pin the steps of one multi-step plan (a script) to the hand-over they were planned
  against, so a step that comes after a later hand-over can tell
- apply_user_control_gate: wrap tool coroutines so a held control stops every tool, and no action runs on a
  surface the person may have changed since the model last looked at it

[POS]
Human-in-control fence shared by the browser and desktop toolkits. Toolkits are independent of each other,
so the fact "a person is driving" lives here and each session only consults it; nothing is pushed into
sessions, which means a session created, cached or pooled after the takeover began is fenced as well.
The fence is tool-level: it stops what the model can call, not processes the agent starts on its own.
`release()` advances `generation`; an action whose model last observed an older generation is refused until
the model observes again, so a plan made before the takeover never executes against the page the person left.
A plan that spans several calls inside one tool call (a script) is pinned the same way with `planned_against`.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator, Mapping

    from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

DEFAULT_WAIT_TIMEOUT_S = 600.0


class UserControlTimeoutError(Exception):
    """The person kept control longer than the caller was willing to wait."""

    def __init__(self, timeout_seconds: float) -> None:
        super().__init__(
            f"A person is still in control after {timeout_seconds:.0f}s, so the action was not run. "
            "Ask them to hand control back, or retry later."
        )
        self.timeout_seconds = timeout_seconds


class UserControl:
    """Whether a person currently drives the agent's surfaces, plus how often control changed hands."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._held = False
        self._generation = 0
        self._waiters: list[asyncio.Future[None]] = []

    @property
    def held(self) -> bool:
        return self._held

    @property
    def generation(self) -> int:
        """Increments each time control returns to the agent."""
        return self._generation

    def acquire(self) -> bool:
        """The person takes control. Returns False when they already hold it."""
        with self._lock:
            if self._held:
                return False
            self._held = True
        logger.info("User control acquired: agent tools are fenced")
        return True

    def release(self) -> bool:
        """Control returns to the agent. Returns False when nobody held it."""
        with self._lock:
            if not self._held:
                return False
            self._held = False
            self._generation += 1
            generation = self._generation
            waiters, self._waiters = self._waiters, []
        for waiter in waiters:
            try:
                waiter.get_loop().call_soon_threadsafe(_resolve, waiter)
            except RuntimeError:
                # The waiter's loop already closed; nobody awaits it, and the rest must still wake.
                continue
        logger.info("User control released (generation=%d)", generation)
        return True

    async def wait_released(self, timeout: float) -> None:
        """Return once the person does not hold control.

        Raises:
            UserControlTimeoutError: the person still holds control after `timeout` seconds.
        """
        if not self._held:
            return
        logger.info("Action waiting: a person holds control (timeout=%.1fs)", timeout)
        deadline = time.monotonic() + timeout
        while self._held:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise UserControlTimeoutError(timeout)
            waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            with self._lock:
                if not self._held:
                    return
                self._waiters.append(waiter)
            try:
                await asyncio.wait_for(waiter, remaining)
            except TimeoutError:
                raise UserControlTimeoutError(timeout) from None
            finally:
                with self._lock:
                    if waiter in self._waiters:
                        self._waiters.remove(waiter)


def _resolve(waiter: asyncio.Future[None]) -> None:
    if not waiter.done():
        waiter.set_result(None)


_PROCESS_CONTROL = UserControl()


def get_user_control() -> UserControl:
    """The one `UserControl` of this process."""
    return _PROCESS_CONTROL


_planned_against: ContextVar[int | None] = ContextVar("user_control_planned_against", default=None)


@contextmanager
def planned_against(generation: int) -> Iterator[None]:
    """Mark the calls made inside as steps of one plan made while control was at `generation`.

    A script is such a plan: it is written from what the model saw, then runs for a while. A step that
    comes after control changed hands was not planned against what the person left on the page.
    """
    token = _planned_against.set(generation)
    try:
        yield
    finally:
        _planned_against.reset(token)


def plan_is_stale(control: UserControl) -> bool:
    """Whether control changed hands since the plan this call belongs to was made; False outside a plan."""
    planned = _planned_against.get()
    return planned is not None and control.generation != planned


class UserControlSurface(Protocol):
    """A session the gate fences: it consults `user_control` and remembers what the model last observed."""

    user_control: UserControl
    observed_generation: int


class ToolRole(StrEnum):
    """What a tool call does to the surface; a tool with no role only waits out the person."""

    OBSERVE = "observe"
    ACT = "act"


type RoleOf = ToolRole | Callable[[Mapping[str, object]], ToolRole | None]


def apply_user_control_gate[ToolT: BaseTool](
    tools: list[ToolT],
    surface: UserControlSurface,
    *,
    roles: Mapping[str, RoleOf],
    exempt: frozenset[str],
    reobserve_notice: str,
    wait_timeout_s: float = DEFAULT_WAIT_TIMEOUT_S,
    timeout_error: Callable[[float], Exception] | None = None,
) -> list[ToolT]:
    """Fence every tool of `surface` behind the person's control, in place.

    While a person holds control every tool but the `exempt` ones waits - reads included, because a
    screenshot taken then shows what they type. Once control is back, an ACT call does not run until an
    OBSERVE call has succeeded since, and an ACT call that waited out a takeover never runs: it returns
    `reobserve_notice` instead. A role may depend on the call's arguments (a tool that both looks and acts).
    `timeout_error` turns the wait timeout into the toolkit's own error; without it `UserControlTimeoutError` rises.

    Raises:
        TypeError: a tool has no coroutine to fence (it would silently stay unfenced).
        ValueError: a classified name matches no tool (a rename would silently drop its protection).
    """
    # Deferred: a bare `import toolkits.browser` must not pay for langchain.
    from langchain_core.tools import StructuredTool

    unknown = (roles.keys() | exempt) - {tool.name for tool in tools}
    if unknown:
        raise ValueError(f"User control gate names unknown tools: {sorted(unknown)}")
    for tool in tools:
        if not isinstance(tool, StructuredTool) or tool.coroutine is None:
            raise TypeError(f"Cannot fence {tool.name}: it has no coroutine")
        if tool.name not in exempt:
            tool.coroutine = _gated(
                tool.coroutine,
                surface,
                role_of=roles.get(tool.name),
                wait_timeout_s=wait_timeout_s,
                timeout_error=timeout_error,
                reobserve_notice=reobserve_notice,
            )
    return tools


def _gated(
    coroutine: Callable[..., Awaitable[object]],
    surface: UserControlSurface,
    *,
    role_of: RoleOf | None,
    wait_timeout_s: float,
    timeout_error: Callable[[float], Exception] | None,
    reobserve_notice: str,
) -> Callable[..., Awaitable[object]]:
    @functools.wraps(coroutine)
    async def run(*args: object, **kwargs: object) -> object:
        control = surface.user_control
        role = role_of(kwargs) if callable(role_of) else role_of
        issued_at = control.generation
        try:
            await control.wait_released(wait_timeout_s)
        except UserControlTimeoutError as exc:
            if timeout_error is None:
                raise
            raise timeout_error(exc.timeout_seconds) from exc
        # Captured before the call: control taken during it must leave the model's observation stale.
        generation = control.generation
        # A call that waited out a takeover was planned against the surface the person has since changed,
        # even if some other tool observed in the meantime: the model has not seen that observation.
        if role is ToolRole.ACT and (generation != issued_at or surface.observed_generation != generation):
            return reobserve_notice
        result = await coroutine(*args, **kwargs)
        if role is ToolRole.OBSERVE:
            surface.observed_generation = generation
        return result

    return run
