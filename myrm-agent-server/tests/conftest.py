from __future__ import annotations

import asyncio
import atexit
import logging
import os
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator, Awaitable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TypeVar

# coverage/pytest-cov patches imports before mcp.types builds RootModel generics.
import pydantic.root_model  # noqa: F401
import pytest
from blockbuster import BlockBuster
from dotenv import load_dotenv

from tests.support.e2e_runtime_guard import (
    E2EResourceLedger,
    assert_e2e_runtime_unchanged,
    e2e_lease_heartbeat_loop,
    require_e2e_runtime_lease,
)
from tests.support.test_secrets import apply_test_secrets_to_environ, load_test_secrets

_SERVER_ROOT = Path(__file__).resolve().parent.parent
_logger = logging.getLogger(__name__)
_T = TypeVar("_T")
_TESTS_ROOT = Path(__file__).resolve().parent
_INTEGRATION_TEST_ROOT = _TESTS_ROOT / "integration"
_E2E_TEST_ROOT = _TESTS_ROOT / "e2e"
_LIFECYCLE_TEST_ROOT = _TESTS_ROOT / "lifecycle"


def _is_formal_chrome_e2e(request: pytest.FixtureRequest) -> bool:
    if request.node.get_closest_marker("chrome_e2e") is not None:
        return True
    if request.node.get_closest_marker("e2e") is None:
        return False
    return Path(request.fspath).resolve().is_relative_to(_E2E_TEST_ROOT)


def _prepend_monorepo_pythonpath() -> None:
    """Prefer monorepo harness src over stale .venv site-packages (batch/skill tests)."""
    import sys

    candidates = (
        _SERVER_ROOT.parent.parent / "myrm-agent-harness" / "src",
        _SERVER_ROOT / "src",
    )
    extra = [str(path) for path in candidates if path.is_dir()]
    if not extra:
        return
    prefix = os.pathsep.join(extra)
    existing = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = f"{prefix}{os.pathsep}{existing}" if existing else prefix
    for path in reversed(extra):
        if path not in sys.path:
            sys.path.insert(0, path)


_prepend_monorepo_pythonpath()

# 1) Process-level .env  2) [T] test secrets via structured loader (not raw load_dotenv)
load_dotenv(_SERVER_ROOT / ".env", override=False)
apply_test_secrets_to_environ()

# Setup isolated workspace - runs at import time
_temp_workspace = tempfile.mkdtemp(prefix=f"myrm_test_{os.getpid()}_")
os.environ["MYRM_DATA_DIR"] = _temp_workspace


def _cleanup_temp_workspace() -> None:
    try:
        shutil.rmtree(_temp_workspace, ignore_errors=True)
    except Exception:
        pass


atexit.register(_cleanup_temp_workspace)


def _cleanup_browser_child_processes() -> None:
    try:
        from tests.support.browser_process_cleanup import terminate_browser_processes_in_tree

        terminate_browser_processes_in_tree(os.getpid())
    except Exception as exc:
        _logger.warning("Failed to cleanup browser child processes: %s", exc)


atexit.register(_cleanup_browser_child_processes)


def _run_async_teardown(coro: Awaitable[_T]) -> _T:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


async def _shutdown_test_session_resources_async() -> None:
    from app.core.memory.adapters.setup import shutdown_cached_memory_managers
    from app.platform_utils import reset_database_engine

    await shutdown_cached_memory_managers()
    await reset_database_engine()


def _shutdown_test_session_resources() -> None:
    """Release session-scoped DB engine and cached memory managers."""
    try:
        _run_async_teardown(_shutdown_test_session_resources_async())
    except Exception as exc:
        _logger.warning("Failed to shutdown test session resources: %s", exc)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    _cleanup_browser_child_processes()
    _shutdown_test_session_resources()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Align benchmark markers with the default memory-safe suite filter."""
    for item in items:
        if item.get_closest_marker("benchmark") is not None and item.get_closest_marker("performance") is None:
            item.add_marker(pytest.mark.performance)
        if item.get_closest_marker("chrome_e2e") is not None:
            existing = item.get_closest_marker("timeout")
            if existing is None or int(existing.args[0]) < 900:
                item.add_marker(pytest.mark.timeout(900))


def _needs_browser_singleton_reset(request: pytest.FixtureRequest) -> bool:
    """Return whether a test may touch the GlobalBrowserPool singleton."""
    item_path = Path(request.fspath).resolve()
    if item_path.is_relative_to(_INTEGRATION_TEST_ROOT):
        return True
    if item_path.is_relative_to(_E2E_TEST_ROOT):
        return True
    if item_path.is_relative_to(_LIFECYCLE_TEST_ROOT):
        return True
    if request.node.get_closest_marker("integration") is not None:
        return True
    return (
        request.node.get_closest_marker("e2e") is not None
        or request.node.get_closest_marker("chrome_e2e") is not None
    )


@pytest.fixture(scope="session")
def test_secrets():
    """Session-scoped [T] secrets fixture for new tests."""
    return load_test_secrets()


# Ensure schema is created since TestClient bypasses lifespan
@pytest.fixture(scope="session", autouse=True)
def init_test_database():
    """Initialize database schema for isolated test DBs."""
    from app.database.connection import init_database

    try:
        asyncio.run(init_database())
    except Exception as e:
        print(f"Warning: init_database failed: {e}")


@pytest.fixture(scope="session", autouse=True)
def _register_server_integration_write_patterns_for_tests() -> None:
    """Mirror main.py startup: register shell integration write patterns for tests."""
    from app.core.security.integration_write_patterns import register_server_integration_write_patterns

    register_server_integration_write_patterns()


# ---------------------------------------------------------------------------
# Blocking-IO runtime detection (blockbuster)
# ---------------------------------------------------------------------------

_SCANNED_MODULES: tuple[str, ...] = ("app",)

_BLOCKING_IO_TEST_ROOT = Path(__file__).resolve().parent / "blocking_io"


@contextmanager
def _blocking_io_gate_ctx() -> Iterator[BlockBuster]:
    """Activate blockbuster scoped to server business code only."""
    bb = BlockBuster(scanned_modules=list(_SCANNED_MODULES))
    try:
        bb.activate()
        yield bb
    finally:
        bb.deactivate()


@pytest.fixture
def blocking_io_gate() -> Iterator[BlockBuster]:
    """Fixture that activates blockbuster for a single test."""
    with _blocking_io_gate_ctx() as bb:
        yield bb


@pytest.fixture(autouse=True)
async def _reset_global_browser_pool_after_test(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    """Shut down harness GlobalBrowserPool after browser-related tests.

    TestClient bypasses app lifespan, so Chromium instances otherwise accumulate
    for the lifetime of each xdist worker process. Scoped to integration/e2e
    paths to avoid async fixture overhead on the full default suite.
    """
    yield
    if not _needs_browser_singleton_reset(request):
        return

    try:
        from myrm_agent_harness.toolkits.browser.pool import reset_global_browser_pool_for_tests

        with suppress(Exception):
            await reset_global_browser_pool_for_tests()
    except Exception as exc:
        _logger.warning("Failed to reset GlobalBrowserPool after test: %s", exc)


@pytest.fixture(autouse=True)
def _chrome_e2e_item_runtime(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[object | None]:
    """Give each formal Chrome item its own private Backend and data directories."""
    marker = request.node.get_closest_marker("chrome_e2e")
    lane = str(marker.kwargs.get("lane", "")).strip().upper() if marker else ""
    if marker is not None and lane not in {"READ", "LIVE_AGENT"}:
        raise RuntimeError(
            "CHROME_E2E_MARKER_INVALID: lane must be READ or LIVE_AGENT"
        )
    private_backend = marker is not None and marker.kwargs.get("private_backend", True) is not False
    if private_backend and lane != "LIVE_AGENT":
        raise RuntimeError(
            "CHROME_E2E_MARKER_INVALID: private Backend items require lane=LIVE_AGENT"
        )
    if (
        marker is None
        or not private_backend
        or os.environ.get("MYRM_E2E_ISOLATED", "").strip() == "1"
        or os.environ.get("MYRM_E2E_PRIVATE_BACKEND", "").strip() == "1"
    ):
        yield None
        return

    require_e2e_runtime_lease()
    import sys

    dev_infra = _SERVER_ROOT.parents[1] / "scripts/dev"
    if str(dev_infra) not in sys.path:
        sys.path.insert(0, str(dev_infra))
    from chrome_e2e_runtime import start_chrome_e2e_runtime

    runtime = start_chrome_e2e_runtime(request.node.nodeid)
    for key, value in runtime.environment.items():
        monkeypatch.setenv(key, value)
    print(
        "CHROME_E2E_RUNTIME: "
        f"item={request.node.name} runtime={runtime.runtime_id} "
        f"api={runtime.api_base} startup={runtime.startup_seconds:.2f}s"
    )
    try:
        yield runtime
    finally:
        runtime.close()


@pytest.fixture(autouse=True)
def _require_live_e2e_lease(
    request: pytest.FixtureRequest,
    _chrome_e2e_item_runtime: object | None,
) -> Iterator[None]:
    """Fail live E2E before side effects when Wave ownership is missing or drifts."""
    if not _is_formal_chrome_e2e(request):
        yield
        return
    lease = require_e2e_runtime_lease()
    from tests.support.e2e_runtime_guard import assert_chrome_attach_health

    try:
        assert_chrome_attach_health()
    except RuntimeError as exc:
        pytest.fail(str(exc))
    namespace = f"pytest-{request.node.name}-{uuid.uuid4().hex}"
    os.environ["MYRM_E2E_LEDGER_NAMESPACE"] = namespace
    with e2e_lease_heartbeat_loop():
        yield
    assert_e2e_runtime_unchanged(lease)


@pytest.fixture
def e2e_resource_ledger(request: pytest.FixtureRequest) -> E2EResourceLedger:
    """Register resources created by one live E2E for lease-owned cleanup."""
    if not _is_formal_chrome_e2e(request):
        raise RuntimeError("E2E_LEDGER_REQUIRED: fixture is only valid for e2e tests")
    lease = require_e2e_runtime_lease()
    namespace = os.environ.get("MYRM_E2E_LEDGER_NAMESPACE", "").strip()
    if not namespace:
        namespace = f"pytest-{request.node.name}-{uuid.uuid4().hex}"
        os.environ["MYRM_E2E_LEDGER_NAMESPACE"] = namespace
    return E2EResourceLedger(
        lease_id=lease.lease_id,
        namespace=namespace,
        ephemeral_runtime=os.environ.get("MYRM_E2E_PRIVATE_BACKEND", "").strip() == "1",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Iterator[None]:
    """Auto-gate tests under tests/blocking_io/ with blockbuster.

    Uses ``pytest_runtest_call`` (not ``pytest_runtest_protocol``) so
    session-scoped fixtures like ``init_test_database`` run outside the
    blockbuster gate.
    """
    item_path = Path(item.path).resolve()
    if not item_path.is_relative_to(_BLOCKING_IO_TEST_ROOT):
        yield
        return

    if item.get_closest_marker("allow_blocking_io") is not None:
        yield
        return

    with _blocking_io_gate_ctx():
        yield
