"""A local-skills scan must not run on the event loop.

A scan parses every SKILL.md and runs the security patterns over it, about a second for two dozen skills. Run on the
loop it froze every other request, stream and health check for that long, so the scan runs on a worker thread. The
loop tests make a scan wait for a task that only the event loop can run: the scan returns only when the loop was free.
"""

from __future__ import annotations

import asyncio
import contextvars
import threading
import time
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills.models import Skill
from app.core.skills.providers.local import LocalSkillsProvider
from app.core.skills.store import reader
from app.core.skills.store.service import SkillsService
from app.core.skills.store.user_config import UserSkillConfigManager

# Rides out a loaded host, and still fails a frozen loop within seconds.
_LOOP_SERVED_TIMEOUT_SEC = 3.0


class _LoopProbe:
    """Lets a scan on a worker thread check that the event loop served another request after the scan began."""

    def __init__(self) -> None:
        self._scan_started = threading.Event()
        self._loop_served = threading.Event()

    def enter_scan(self) -> None:
        self._scan_started.set()
        assert self._loop_served.wait(_LOOP_SERVED_TIMEOUT_SEC), "the scan froze the event loop"

    async def serve_another_request(self) -> None:
        """Waits for the scan to begin, so it cannot be served before the scan and prove nothing."""
        while not self._scan_started.is_set():
            await asyncio.sleep(0.001)
        self._loop_served.set()


async def test_list_local_skills_leaves_the_event_loop_free(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    probe = _LoopProbe()

    def scan_all(_self: LocalSkillsProvider) -> list[Skill]:
        probe.enter_scan()
        return []

    monkeypatch.setattr("app.core.skills.providers.local.is_sandbox_mode", lambda: False)
    monkeypatch.setattr(LocalSkillsProvider, "scan_all", scan_all)
    manager = UserSkillConfigManager(LocalStorageBackend(str(tmp_path)))

    other_request = asyncio.create_task(probe.serve_another_request())
    assert await reader.list_local_skills(manager) == []
    await other_request


async def test_get_local_skill_leaves_the_event_loop_free(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    probe = _LoopProbe()

    def get_skill_by_id(_self: LocalSkillsProvider, _skill_id: str) -> Skill | None:
        probe.enter_scan()
        return None

    monkeypatch.setattr("app.core.skills.store.service.is_sandbox_mode", lambda: False)
    monkeypatch.setattr(LocalSkillsProvider, "get_skill_by_id", get_skill_by_id)
    service = SkillsService(LocalStorageBackend(str(tmp_path)))

    other_request = asyncio.create_task(probe.serve_another_request())
    assert await service.get_skill("local::deadbeef") is None
    await other_request


async def test_scan_off_loop_runs_on_a_worker_thread_with_the_callers_context() -> None:
    request_id = contextvars.ContextVar[str]("request_id")
    request_id.set("request-7")

    worker_thread, seen_request_id = await reader.scan_off_loop(lambda: (threading.get_ident(), request_id.get()))

    assert worker_thread != threading.get_ident()
    assert seen_request_id == "request-7"


async def test_scan_off_loop_runs_one_scan_at_a_time() -> None:
    lock = threading.Lock()
    running = 0
    peak = 0

    def scan() -> None:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.02)
        with lock:
            running -= 1

    await asyncio.gather(*(reader.scan_off_loop(scan) for _ in range(4)))

    assert peak == 1


async def test_scan_off_loop_propagates_the_scans_error() -> None:
    def failing_scan() -> None:
        raise PermissionError("denied")

    with pytest.raises(PermissionError, match="denied"):
        await reader.scan_off_loop(failing_scan)
