"""Backend log of the stack under test.

[INPUT]
- cdp_chat.support.api_client::_is_shared_dev_api_url, get_e2e_api_url (POS: Where the E2E API and UI live and the loopback-only HTTP calls to them, retried under parallel load)
- cdp_chat.support.binding::_E2E_RUNTIME_ID_RE (POS: Binds the chat page to the backend under test: the scripts that put the runtime identity and API base into the page, and the check that the page reports the expected one)
- cdp_chat.support.paths::MONOREPO_ROOT (POS: Single source of the checkout root the E2E helpers resolve dev scripts and stack state against)
- e2e_core.real_user_home::real_user_home (POS: real login user home, bypassing a sandboxed HOME)

[OUTPUT]
- backend_log_path, snapshot_backend_log_offset: the log of the stack a run talks to and its current size
- dump_backend_log_on_failure: print what the backend logged inside a block that raised
- private_backend_log_offset, print_private_backend_log_since: the same for the session's private runtime only
- count_execution_cache_in_log, count_turn_prewarm_in_log: counters over the log text since an offset

[POS]
Finds the backend.log of the stack under test and reads what it recorded during a run.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

from e2e_core.real_user_home import real_user_home

from cdp_chat.support.api_client import _is_shared_dev_api_url, get_e2e_api_url
from cdp_chat.support.binding import _E2E_RUNTIME_ID_RE
from cdp_chat.support.paths import MONOREPO_ROOT


def _isolated_root() -> Path:
    override = os.getenv("MYRM_ISOLATED_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return real_user_home() / ".local/state/myrm-isolated"


def _private_runtime_backend_log(api_url: str | None) -> Path | None:
    """Map a SHPOIB/PRIVATE API port to its isolated runtime backend.log.

    pytest's own env keeps ``MYRM_DEV_STATE_DIR`` on the shared stack while
    PRIVATE items talk to a per-session backend whose log lives under the
    isolated runtime stateDir. Resolve that log from the isolated runtime
    registry (``backendPort`` -> ``stateDir``) so log assertions read the
    backend that actually served the session instead of the shared one.
    """
    resolved = api_url or os.getenv("E2E_API_BASE", "").strip()
    if not resolved:
        return None
    try:
        port = urlsplit(resolved).port
    except ValueError:
        return None
    if port is None or _is_shared_dev_api_url(resolved):
        return None
    registry = _isolated_root() / "registry.json"
    if not registry.is_file():
        return None
    try:
        payload = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    records = payload.get("runtimes") if isinstance(payload, dict) else None
    if not isinstance(records, dict):
        return None
    for record in records.values():
        if not isinstance(record, dict):
            continue
        if record.get("backendPort") == port:
            state_dir = record.get("stateDir")
            if isinstance(state_dir, str) and state_dir:
                candidate = Path(state_dir) / "backend.log"
                if candidate.is_file():
                    return candidate
    return None


def backend_log_path(api_url: str | None = None) -> Path:
    override = os.getenv("MYRM_BACKEND_LOG", "").strip()
    if not override:
        override = os.getenv("MYRM_BACKEND_LOG_FILE", "").strip()
    if override:
        return Path(override)
    private = _private_runtime_backend_log(api_url)
    if private is not None:
        return private
    state_dir = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    if state_dir:
        return Path(state_dir) / "backend.log"
    default = real_user_home() / ".local/state/myrm-dev/backend.log"
    if default.is_file():
        return default
    server_root = MONOREPO_ROOT / "myrm-agent" / "myrm-agent-server"
    return server_root / ".myrm-dev-backend.log"


def snapshot_backend_log_offset(api_url: str | None = None) -> int:
    path = backend_log_path(api_url=api_url)
    if not path.is_file():
        return 0
    return path.stat().st_size


_FAILURE_LOG_TAIL_BYTES = 64_000
_SEND_FAILURE_LOG_TAIL_BYTES = 131_072


def _print_backend_log_since(path: Path, offset: int, *, tail_bytes: int) -> None:
    """Print ``path`` from ``offset`` on, at most the newest ``tail_bytes``.

    Never raises: the report explains a failure and must not replace it, and the
    runtime that owns the log can be reaped while it is read.
    """
    try:
        size = path.stat().st_size
        # A log shorter than the recorded offset was truncated or rotated mid-block.
        start = offset if offset <= size else 0
        with path.open("rb") as handle:
            handle.seek(max(start, size - tail_bytes))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return
    print(
        f"\nBACKEND_LOG_ON_FAILURE ({path}):\n{text}\nBACKEND_LOG_ON_FAILURE_END",
        flush=True,
    )


@contextlib.contextmanager
def dump_backend_log_on_failure(
    api_url: str | None = None,
    *,
    tail_bytes: int = _FAILURE_LOG_TAIL_BYTES,
) -> Iterator[None]:
    """Print the backend log written during the block when it raises.

    PRIVATE runtimes are reaped at teardown together with their ``backend.log``,
    so a failed live flow would otherwise leave no server-side evidence.
    """
    start = snapshot_backend_log_offset(api_url=api_url)
    try:
        yield
    except BaseException:
        _print_backend_log_since(
            backend_log_path(api_url=api_url), start, tail_bytes=tail_bytes
        )
        raise


def _session_private_backend_log() -> Path | None:
    """This session's private-runtime ``backend.log``; None on the shared stack.

    Inside a private runtime the allocator exports the runtime id together with
    ``MYRM_BACKEND_PORT`` set to the private port, so the API URL looks like "the
    current backend" and the registry lookup below treats it as shared. The id names
    the log's canonical place directly, and building the path from it (never from a
    ``MYRM_BACKEND_LOG*`` override, which may be stale) cannot reach another stack's log.
    """
    runtime_id = os.getenv("MYRM_E2E_PRIVATE_RUNTIME_ID", "").strip()
    if runtime_id:
        if not _E2E_RUNTIME_ID_RE.fullmatch(runtime_id):
            return None
        candidate = _isolated_root() / "runtimes" / runtime_id / "state" / "backend.log"
        return candidate if candidate.is_file() else None
    try:
        return _private_runtime_backend_log(get_e2e_api_url())
    except RuntimeError:
        # An unusable E2E_API_BASE already fails the send itself, loudly.
        return None


def private_backend_log_offset() -> int:
    """Size of the session's private ``backend.log`` now; 0 without one."""
    path = _session_private_backend_log()
    if path is None:
        return 0
    try:
        return path.stat().st_size
    except OSError:
        return 0


def print_private_backend_log_since(offset: int) -> None:
    """Print what the session's private backend logged since ``offset``.

    Unlike ``dump_backend_log_on_failure`` there is no fallback to the shared or the
    developer's own dev-stack log: a test failure never reads a stack it does not own.
    """
    path = _session_private_backend_log()
    if path is not None:
        _print_backend_log_since(path, offset, tail_bytes=_SEND_FAILURE_LOG_TAIL_BYTES)


def count_execution_cache_in_log(
    *,
    since_offset: int,
    api_url: str | None = None,
) -> tuple[int, int]:
    path = backend_log_path(api_url=api_url)
    if not path.is_file():
        return 0, 0
    with path.open("rb") as handle:
        handle.seek(since_offset)
        chunk = handle.read()
    text = chunk.decode("utf-8", errors="replace")
    created = text.count("execution_cache_created")
    reused = text.count("execution_cache_reuse")
    return created, reused


def count_turn_prewarm_in_log(
    *,
    since_offset: int,
    api_url: str | None = None,
) -> int:
    """Count ``Turn prewarm requested`` log lines (EmptyChat / focus proactive warm)."""
    path = backend_log_path(api_url=api_url)
    if not path.is_file():
        return 0
    with path.open("rb") as handle:
        handle.seek(since_offset)
        chunk = handle.read()
    text = chunk.decode("utf-8", errors="replace")
    return text.count("Turn prewarm requested")
