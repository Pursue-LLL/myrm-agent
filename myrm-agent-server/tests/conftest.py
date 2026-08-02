from __future__ import annotations

import asyncio
import atexit
import fcntl
import logging
import os
import shutil
import sys
import tempfile
import uuid
from collections.abc import Awaitable, Iterator
from contextlib import contextmanager, nullcontext, suppress
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
_DEV_LIB = _SERVER_ROOT.parent / "scripts" / "dev" / "lib"
if str(_DEV_LIB) not in sys.path:
    sys.path.insert(0, str(_DEV_LIB))
from dev_gate_contract import (  # noqa: E402
    chrome_e2e_pytest_timeout_floor,
)

_logger = logging.getLogger(__name__)
_T = TypeVar("_T")
_TESTS_ROOT = Path(__file__).resolve().parent
_INTEGRATION_TEST_ROOT = _TESTS_ROOT / "integration"
_E2E_TEST_ROOT = _TESTS_ROOT / "e2e"
_LIFECYCLE_TEST_ROOT = _TESTS_ROOT / "lifecycle"
_CHROME_PROFILE_FIELDS = frozenset(
    {"execution_mode", "access_scope", "workload"}
)


def _is_formal_chrome_e2e(item_or_request: pytest.Item | pytest.FixtureRequest) -> bool:
    if isinstance(item_or_request, pytest.Item):
        node = item_or_request
    elif hasattr(item_or_request, "node"):
        node = item_or_request.node
    else:
        return False
    if not isinstance(node, pytest.Item):
        return False
    if node.get_closest_marker("chrome_e2e") is not None:
        return True
    if node.get_closest_marker("e2e") is None:
        return False
    return Path(node.fspath).resolve().is_relative_to(_E2E_TEST_ROOT)


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
        from tests.support.browser_process_cleanup import (
            terminate_browser_processes_in_tree,
        )

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


def _chrome_e2e_timeout_failure(item: pytest.Item, rep: pytest.TestReport) -> bool:
    if item.get_closest_marker("chrome_e2e") is None:
        return False
    if not rep.failed:
        return False
    if rep.when not in {"call", "setup", "teardown"}:
        return False
    longrepr = str(rep.longrepr or "").lower()
    return "timeout" in longrepr or "timed out" in longrepr


@pytest.hookimpl(specname="pytest_runtest_makereport", hookwrapper=True)
def pytest_runtest_makereport_signoff(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Iterator[None]:
    """Release DB/MCP hygiene when a formal chrome_e2e item hits pytest-timeout."""
    outcome = yield
    rep = outcome.get_result()
    if not _chrome_e2e_timeout_failure(item, rep):
        return
    from tests.support.e2e_runtime_guard import reap_chrome_e2e_session_hygiene

    _logger.warning(
        "Chrome E2E timeout hygiene for %s (%s): reaping session resources",
        item.nodeid,
        rep.when,
    )
    try:
        reap_chrome_e2e_session_hygiene()
    except Exception as exc:
        _logger.warning(
            "Failed to reap chrome E2E session hygiene after timeout: %s", exc
        )
    try:
        _shutdown_test_session_resources()
    except Exception as exc:
        _logger.warning(
            "Failed to shutdown test session resources after timeout: %s", exc
        )


def _chrome_e2e_marker_joined_argv(item: pytest.Item) -> str:
    parts: list[str] = []
    for marker in item.iter_markers():
        if marker.name == "chrome_e2e":
            workload = str(marker.kwargs.get("workload", "")).strip().upper()
            if workload:
                parts.append(f"workload={workload}")
        elif marker.name == "chrome_e2e_signoff_batch":
            parts.append(marker.name)
            body_sec = marker.kwargs.get("body_sec")
            if body_sec is not None:
                parts.append(f"body_sec={int(body_sec)}")
        else:
            parts.append(marker.name)
    return " ".join(parts)


def _chrome_e2e_lane_timeout_sec(item: pytest.Item) -> int | None:
    marker = item.get_closest_marker("chrome_e2e")
    if marker is None:
        return None
    profile = _chrome_e2e_profile(item)
    if profile is None:
        return None
    _execution_mode, _access_scope, workload = profile
    lane = "READ" if workload == "STANDARD" else "LIVE_AGENT"
    return chrome_e2e_pytest_timeout_floor(lane, _chrome_e2e_marker_joined_argv(item))


def _chrome_e2e_profile(
    item: pytest.Item,
) -> tuple[str, str, str] | None:
    marker = item.get_closest_marker("chrome_e2e")
    if marker is None:
        return None
    fields = frozenset(marker.kwargs)
    missing = sorted(_CHROME_PROFILE_FIELDS - fields)
    unknown = sorted(fields - _CHROME_PROFILE_FIELDS)
    if missing or unknown:
        raise pytest.UsageError(
            "CHROME_E2E_PROFILE_INVALID: "
            f"node={item.nodeid} missing={','.join(missing) or '-'} "
            f"unknown={','.join(unknown) or '-'}"
        )
    execution_mode = str(marker.kwargs["execution_mode"]).strip().upper()
    access_scope = str(marker.kwargs["access_scope"]).strip().upper()
    workload = str(marker.kwargs["workload"]).strip().upper()
    if execution_mode not in {"SHARED", "PRIVATE"}:
        raise pytest.UsageError(
            f"CHROME_E2E_PROFILE_INVALID: node={item.nodeid} "
            f"execution_mode={execution_mode!r}"
        )
    if access_scope not in {"READ", "NAMESPACE_WRITE", "GLOBAL_WRITE"}:
        raise pytest.UsageError(
            f"CHROME_E2E_PROFILE_INVALID: node={item.nodeid} "
            f"access_scope={access_scope!r}"
        )
    if workload not in {"STANDARD", "LIVE", "DESKTOP"}:
        raise pytest.UsageError(
            f"CHROME_E2E_PROFILE_INVALID: node={item.nodeid} workload={workload!r}"
        )
    if execution_mode == "SHARED" and access_scope == "GLOBAL_WRITE":
        raise pytest.UsageError(
            f"CHROME_E2E_PROFILE_UNSAFE: node={item.nodeid} "
            "SHARED+GLOBAL_WRITE is forbidden"
        )
    return execution_mode, access_scope, workload


def _apply_chrome_e2e_lane_timeout(item: pytest.Item) -> None:
    floor = _chrome_e2e_lane_timeout_sec(item)
    if floor is None:
        return
    # R43: always cap chrome_e2e to lane floor; per-item marks must not exceed SSOT.
    item.own_markers = [
        marker for marker in item.own_markers if marker.name != "timeout"
    ]
    item.add_marker(pytest.mark.timeout(floor))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Align benchmark markers with the default memory-safe suite filter."""
    for item in items:
        if (
            item.get_closest_marker("benchmark") is not None
            and item.get_closest_marker("performance") is None
        ):
            item.add_marker(pytest.mark.performance)
        if item.get_closest_marker("chrome_e2e") is not None:
            _chrome_e2e_profile(item)
            _apply_chrome_e2e_lane_timeout(item)


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
_INIT_DB_LOCK = Path(tempfile.gettempdir()) / "myrm-server-pytest-init-db.lock"


@pytest.fixture(scope="session", autouse=True)
def init_test_database():
    """Initialize database schema for isolated test DBs."""
    # Formal chrome_e2e runs against the live server stack; parallel pytest
    # processes must not race init_database() on the shared SQLite file.
    if os.environ.get("MYRM_E2E_LANE", "").strip() in {"READ", "LIVE_AGENT"}:
        return

    from app.database.connection import init_database

    _INIT_DB_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with _INIT_DB_LOCK.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            _run_async_teardown(init_database())
        except Exception as e:
            print(f"Warning: init_database failed: {e}")
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@pytest.fixture(scope="session", autouse=True)
def _register_server_integration_write_patterns_for_tests() -> None:
    """Mirror main.py startup: register shell integration write patterns for tests."""
    from app.core.security.integration_write_patterns import (
        register_server_integration_write_patterns,
    )

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
def _reset_global_browser_pool_after_test(
    request: pytest.FixtureRequest,
) -> Iterator[None]:
    """Shut down harness GlobalBrowserPool after browser-related tests.

    TestClient bypasses app lifespan, so Chromium instances otherwise accumulate
    for the lifetime of each xdist worker process. Scoped to integration/e2e
    paths to avoid async fixture overhead on the full default suite.
    """
    yield
    if not _needs_browser_singleton_reset(request):
        return

    try:
        from myrm_agent_harness.toolkits.browser.pool import (
            reset_global_browser_pool_for_tests,
        )

        with suppress(Exception):
            _run_async_teardown(reset_global_browser_pool_for_tests())
    except Exception as exc:
        _logger.warning("Failed to reset GlobalBrowserPool after test: %s", exc)


def _e2e_dev_lib_path() -> Path:
    return _SERVER_ROOT.parents[1] / "scripts" / "dev" / "lib"


def _epoch_drift_entry_skip_if_shared(request: pytest.FixtureRequest) -> None:
    """Layer-1 entry gate: skip SHARED tests immediately when epoch drift is active.

    Prevents lease acquisition under epoch mismatch, breaking the deadlock cycle
    where held leases block system restart which would resolve the epoch drift.
    """
    if os.environ.get("MYRM_E2E_EPOCH_DRIFT_GUARD_DISABLE", "").strip() == "1":
        return
    # R278/R279: signoff + desktop soak queue via ADMIT — never pytest.skip here.
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        return
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() == "1":
        return
    profile = _chrome_e2e_profile(request.node)
    if profile is None:
        return
    execution_mode = profile[0]
    if execution_mode == "PRIVATE":
        return

    dev_lib = _e2e_dev_lib_path()
    if str(dev_lib) not in sys.path:
        sys.path.insert(0, str(dev_lib))
    try:
        from e2e_api_verify import resolve_e2e_api_context

        ctx = resolve_e2e_api_context(retry_after_apply=False)
    except Exception:
        return

    if ctx.epoch_match or not ctx.blocked:
        return

    pytest.skip(
        f"epoch drift entry gate: shared backend epoch mismatch "
        f"(blocked={ctx.blocked_reason!r}). "
        f"Skipping to avoid lease acquisition under drift — "
        f"system will auto-restart once all leases are released."
    )


@pytest.fixture(autouse=True)
def _chrome_e2e_item_runtime(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[object | None]:
    """Give every PRIVATE Chrome item an isolated per-item Backend."""
    profile = _chrome_e2e_profile(request.node)
    if profile is None:
        yield None
        return
    execution_mode, _access_scope, workload = profile
    private_runtime = execution_mode == "PRIVATE"
    if (
        not private_runtime
        or os.environ.get("MYRM_E2E_ISOLATED", "").strip() == "1"
        or os.environ.get("MYRM_E2E_PRIVATE_BACKEND", "").strip() == "1"
    ):
        yield None
        return

    from tests.support.e2e_runtime_guard import reap_chrome_e2e_session_hygiene

    reap_chrome_e2e_session_hygiene()
    require_e2e_runtime_lease()
    import sys

    dev_infra = _SERVER_ROOT.parents[1] / "scripts/dev"
    if str(dev_infra) not in sys.path:
        sys.path.insert(0, str(dev_infra))
    from e2e_orchestrator import begin_bootstrap_phase
    from e2e_session_snapshot import write_session_snapshot

    begin_bootstrap_phase(phase_label=request.node.name)
    write_session_snapshot(
        current_node=request.node.nodeid,
        phase="bootstrap",
    )
    from chrome_e2e_runtime import start_chrome_e2e_runtime

    runtime_lane = "READ" if workload == "STANDARD" else "LIVE_AGENT"
    runtime = start_chrome_e2e_runtime(
        request.node.nodeid,
        backend_only=True,
        lane=runtime_lane,
    )
    for key, value in runtime.environment.items():
        monkeypatch.setenv(key, value)
    print(
        "CHROME_E2E_RUNTIME: "
        f"item={request.node.name} runtime={runtime.runtime_id} "
        f"api={runtime.api_base} ui={runtime.environment.get('E2E_UI_BASE', '')} "
        f"startup={runtime.startup_seconds:.2f}s"
    )
    try:
        yield runtime
    finally:
        try:
            runtime.close()
        except RuntimeError as exc:
            print(f"CHROME_E2E_RUNTIME_CLOSE_WARN: {exc}", flush=True)


@pytest.fixture(autouse=True)
def _require_live_e2e_lease(
    request: pytest.FixtureRequest,
    _chrome_e2e_item_runtime: object | None,
) -> Iterator[None]:
    """Fail live E2E before side effects when Wave ownership is missing or drifts."""
    if not _is_formal_chrome_e2e(request):
        yield
        return
    if (
        os.environ.get("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "").strip() == "1"
        and os.environ.get("MYRM_E2E_API_ONLY", "").strip() == "1"
    ):
        yield
        return
    from tests.support.e2e_runtime_guard import (
        assert_chrome_attach_health,
        reap_chrome_e2e_session_hygiene,
        _heal_stale_e2e_lease,
    )

    runtime_cell_id: str | None = None
    _release_runtime_cell = None
    try:
        from e2e_runtime_cell import allocate_runtime_cell, release_runtime_cell

        runtime_cell = allocate_runtime_cell()
        runtime_cell_id = runtime_cell.cell_id
        _release_runtime_cell = release_runtime_cell
    except ImportError:
        pass

    try:
        _epoch_drift_entry_skip_if_shared(request)
        reap_chrome_e2e_session_hygiene()
        _heal_stale_e2e_lease()
        lease = require_e2e_runtime_lease()

        dev_infra = _SERVER_ROOT.parents[1] / "scripts/dev"
        if str(dev_infra) not in sys.path:
            sys.path.insert(0, str(dev_infra))
        from dev_gate_contract import chrome_e2e_skips_attach_health_reprobe

        try:
            # Item runtimes already run chrome-e2e-preflight with attach checks on their env.
            skip_attach_reprobe = chrome_e2e_skips_attach_health_reprobe(
                chrome_attach=os.environ.get("MYRM_CHROME_E2E_ATTACH", "").strip()
                == "1",
                api_only=os.environ.get("MYRM_E2E_API_ONLY", "").strip() == "1"
                or os.environ.get("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "").strip() == "1",
            )
            if _chrome_e2e_item_runtime is None and not skip_attach_reprobe:
                assert_chrome_attach_health()
            elif skip_attach_reprobe:
                print(
                    "MYRM_TEST: skip attach health reprobe (bootstrap verified)",
                    flush=True,
                )
        except RuntimeError as exc:
            pytest.fail(str(exc))
        from e2e_orchestrator import begin_bootstrap_phase

        begin_bootstrap_phase(phase_label=request.node.name)
        from e2e_session_snapshot import write_session_snapshot

        write_session_snapshot(
            current_node=request.node.nodeid,
            phase="bootstrap",
        )
        reap_chrome_e2e_session_hygiene()
        from e2e_signoff_trace import begin_signoff_trace

        begin_signoff_trace(nodeid=request.node.nodeid)
        namespace = f"pytest-{request.node.name}-{uuid.uuid4().hex}"
        os.environ["MYRM_E2E_LEDGER_NAMESPACE"] = namespace
        with nullcontext():
            from e2e_shared_ui_session import (
                E2E_SEARCH_POLICY_ENV,
                prime_search_policy_env,
            )

            prime_search_policy_env(request.node)
            lib = _e2e_dev_lib_path()
            if str(lib) not in sys.path:
                sys.path.insert(0, str(lib))
            from e2e_session_lifecycle import begin_bootstrap_phase

            begin_bootstrap_phase(phase_label="page_open_pending")
            write_session_snapshot(
                current_node=request.node.nodeid,
                phase="bootstrap",
            )
            try:
                with e2e_lease_heartbeat_loop():
                    yield
                    reap_chrome_e2e_session_hygiene()
            finally:
                os.environ.pop(E2E_SEARCH_POLICY_ENV, None)
        assert_e2e_runtime_unchanged(lease)
    finally:
        if runtime_cell_id and _release_runtime_cell is not None:
            _release_runtime_cell(runtime_cell_id)


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
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Iterator[None]:
    outcome = yield
    rep = outcome.get_result()
    if call.when != "call" or not _is_formal_chrome_e2e(item):
        return
    dev_infra = _SERVER_ROOT.parents[1] / "scripts/dev"
    if str(dev_infra) not in sys.path:
        sys.path.insert(0, str(dev_infra))
    from e2e_signoff_trace import end_signoff_trace

    if rep.passed:
        end_signoff_trace(outcome="PASSED")
    elif rep.failed:
        end_signoff_trace(outcome="FAILED")
    elif rep.skipped:
        end_signoff_trace(outcome="SKIPPED")


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """R148: orphan signoff trace + session cleanup on abort."""
    del exitstatus
    if any(_is_formal_chrome_e2e(item) for item in getattr(session, "items", ())):
        dev_infra = _SERVER_ROOT.parents[1] / "scripts/dev"
        if str(dev_infra) not in sys.path:
            sys.path.insert(0, str(dev_infra))
        from e2e_signoff_trace import end_signoff_trace, signoff_trace_path

        if signoff_trace_path() is not None:
            end_signoff_trace(outcome="INTERRUPTED")
    _cleanup_browser_child_processes()
    _shutdown_test_session_resources()


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
