"""The boot pauses the cycle collector and ends the pause once start-up has settled.

[INPUT]
- app.startup.gc_policy (POS: pause, freeze-and-resume, settle-after)
- app.startup.uvicorn_runner::start_with_uvicorn (POS: the entry that pauses the collector before importing the app)

[OUTPUT]
- Regression coverage of the pause, the freeze-then-resume, the deadline and the entry ordering

[POS]
Startup tests. The collector is process-global, so every test restores it (running, nothing frozen) and the rest of
the suite keeps the default policy.
"""

from __future__ import annotations

import ast
import asyncio
import gc
import inspect
from collections.abc import Iterator

import pytest

from app.startup import uvicorn_runner
from app.startup.gc_policy import defer_collection, settle_collection, settle_collection_after


@pytest.fixture(autouse=True)
def _restore_collector() -> Iterator[None]:
    was_enabled = gc.isenabled()
    yield
    gc.unfreeze()
    if was_enabled:
        gc.enable()
    else:
        gc.disable()


def test_deferring_pauses_the_collector() -> None:
    gc.enable()

    defer_collection()

    assert not gc.isenabled()


def test_settling_freezes_the_boot_heap_and_resumes_collection() -> None:
    defer_collection()
    frozen_before = gc.get_freeze_count()

    settle_collection()

    assert gc.isenabled()
    assert gc.get_freeze_count() > frozen_before


def test_settling_a_running_collector_changes_nothing() -> None:
    """Tests and tools that import `app` never paused the collector; settling must not freeze their heap."""
    gc.enable()
    frozen_before = gc.get_freeze_count()

    settle_collection()

    assert gc.isenabled()
    assert gc.get_freeze_count() == frozen_before


async def test_settling_after_boot_work_waits_for_it() -> None:
    boot_work: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    defer_collection()

    settle_collection_after(boot_work, deadline_seconds=60)
    await asyncio.sleep(0.01)
    assert not gc.isenabled()

    boot_work.set_result(None)
    await asyncio.sleep(0.01)
    assert gc.isenabled()


async def test_settling_after_boot_work_that_failed_still_resumes_collection() -> None:
    boot_work: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    defer_collection()
    settle_collection_after(boot_work, deadline_seconds=60)

    boot_work.set_exception(RuntimeError("warmup failed"))
    await asyncio.sleep(0.01)

    assert gc.isenabled()
    assert isinstance(boot_work.exception(), RuntimeError)


async def test_settling_after_the_deadline_when_boot_work_never_ends() -> None:
    """A hung warmup must not leave the process without cycle collection."""
    boot_work: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    defer_collection()

    settle_collection_after(boot_work, deadline_seconds=0.05)
    assert not gc.isenabled()
    await asyncio.sleep(0.3)

    assert gc.isenabled()
    boot_work.cancel()


def test_the_uvicorn_entry_pauses_the_collector_before_importing_the_app() -> None:
    """The import is where the pauses add up; a later pause would find the damage done."""
    tree = ast.parse(inspect.getsource(uvicorn_runner.start_with_uvicorn))
    pauses = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "defer_collection"
    ]
    app_imports = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module == "app.main"]

    assert len(pauses) == 1
    assert len(app_imports) == 1
    assert pauses[0] < app_imports[0]
