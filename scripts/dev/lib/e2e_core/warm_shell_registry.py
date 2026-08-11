"""WarmShellRegistry — epoch-scoped platform shell SSOT for SHARED+READ hot bootstrap (§19.11 TAB-6).

[INPUT]
- e2e_api_verify workspace fingerprint + epoch_match
- MYRM_E2E_EXECUTION_MODE / MYRM_E2E_ACCESS_SCOPE env
- verify-api / warm_ui_route HTTP probes

[OUTPUT]
- seal_platform_shell / platform_shell_fresh / shared_read_hot_path_decision
- bootstrap_hot_path snapshot field via set_bootstrap_hot_path

[POS]
Dev Gate layer — avoids per-test cold openPageTransaction when platform shell already seeded.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal
from urllib.parse import urlsplit, urlunsplit

BootstrapHotPath = Literal["reused", "fast_create", "cold", "skipped"]

_DEFAULT_TTL_SEC = 300.0
_REGISTRY_DIR_NAME = "warm-shell"


@dataclass(frozen=True, slots=True)
class WarmShellRecord:
    workspace_fingerprint: str
    ui_origin: str
    routes: frozenset[str]
    sealed_at: float


@dataclass(frozen=True, slots=True)
class HotPathDecision:
    eligible: bool
    reason: str
    needs_binding: bool


def _state_dir() -> Path:
    raw = os.environ.get(
        "MYRM_E2E_STATE_DIR",
        str(_real_user_home() / ".local" / "state" / "myrm-e2e"),
    )
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _real_user_home() -> Path:
    """Real login home — Cursor sandboxes HOME (~/.cursor2), splitting state."""
    try:
        import pwd

        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError, OSError):
        return Path.home()


def _registry_path(workspace_fp: str) -> Path:
    safe = workspace_fp.strip().replace("/", "_") or "unknown"
    return _state_dir() / _REGISTRY_DIR_NAME / f"{safe}.json"


def _registry_lock_path(workspace_fp: str) -> Path:
    return _registry_path(workspace_fp).with_suffix(".lock")


@contextmanager
def _registry_file_lock(*, workspace_fp: str) -> Iterator[None]:
    fp = workspace_fp.strip()
    if not fp:
        yield
        return
    lock_path = _registry_lock_path(fp)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write_registry_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _normalize_route(path: str) -> str:
    text = path.strip()
    if not text.startswith("/"):
        text = f"/{text}"
    if text != "/" and text.endswith("/"):
        text = text.rstrip("/")
    return text or "/"


def _ui_origin(url: str) -> str:
    parsed = urlsplit(url.strip())
    port = parsed.port
    host = (parsed.hostname or "127.0.0.1").lower()
    scheme = parsed.scheme or "http"
    if port is None:
        port = 443 if scheme == "https" else 80
    netloc = f"{host}:{port}" if port not in (80, 443) else host
    return urlunsplit((scheme, netloc, "", "", ""))


def current_workspace_fingerprint() -> str:
    """Workspace FP without verify-api port scan (TAB-6b open_mcp_page hot path)."""
    try:
        from e2e_api_verify import workspace_backend_fingerprint

        return workspace_backend_fingerprint().strip()
    except ImportError:
        pass
    try:
        from runtime_identity import _backend_source_fingerprint

        return _backend_source_fingerprint().strip()
    except ImportError:
        return ""


def epoch_aligned() -> bool:
    """Epoch alignment from stack-epoch.json — no backend candidate enumeration."""
    try:
        from runtime_identity import read_backend_epoch

        epoch = read_backend_epoch()
        if epoch is not None:
            return bool(epoch.get("epoch_match", False))
    except ImportError:
        pass
    return False


def read_platform_shell(*, workspace_fp: str | None = None) -> WarmShellRecord | None:
    fp = (workspace_fp or current_workspace_fingerprint()).strip()
    if not fp:
        return None
    path = _registry_path(fp)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    ui_origin = str(payload.get("uiOrigin") or "").strip()
    sealed_raw = payload.get("sealedAt")
    routes_raw = payload.get("routes")
    if not ui_origin or not isinstance(sealed_raw, (int, float)):
        return None
    routes: set[str] = {"/"}
    if isinstance(routes_raw, list):
        for item in routes_raw:
            if isinstance(item, str) and item.strip():
                routes.add(_normalize_route(item))
    return WarmShellRecord(
        workspace_fingerprint=fp,
        ui_origin=ui_origin,
        routes=frozenset(routes),
        sealed_at=float(sealed_raw),
    )


def seal_platform_shell(
    *,
    ui_url: str,
    route_path: str = "/",
    workspace_fp: str | None = None,
) -> WarmShellRecord | None:
    fp = (workspace_fp or current_workspace_fingerprint()).strip()
    if not fp:
        return None
    origin = _ui_origin(ui_url)
    route = _normalize_route(route_path)
    path = _registry_path(fp)
    with _registry_file_lock(workspace_fp=fp):
        existing_payload: dict[str, object] = {}
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing_payload = loaded
            except (OSError, ValueError, json.JSONDecodeError):
                existing_payload = {}
        routes: set[str] = set()
        routes_raw = existing_payload.get("routes")
        if isinstance(routes_raw, list):
            for item in routes_raw:
                if isinstance(item, str) and item.strip():
                    routes.add(_normalize_route(item))
        routes.add(route)
        sealed_at = time.time()
        payload: dict[str, object] = {
            "workspaceFingerprint": fp,
            "uiOrigin": origin,
            "routes": sorted(routes),
            "sealedAt": sealed_at,
        }
        record = WarmShellRecord(
            workspace_fingerprint=fp,
            ui_origin=origin,
            routes=frozenset(routes),
            sealed_at=sealed_at,
        )
        _write_registry_payload(path, payload)
        return record


def platform_shell_fresh(
    *,
    route_path: str = "/",
    ttl_sec: float = _DEFAULT_TTL_SEC,
    workspace_fp: str | None = None,
) -> bool:
    record = read_platform_shell(workspace_fp=workspace_fp)
    if record is None:
        return False
    route = _normalize_route(route_path)
    if route not in record.routes and route != "/":
        return False
    age = time.time() - record.sealed_at
    return age <= float(ttl_sec)


def shared_read_hot_path_decision(*, url: str) -> HotPathDecision:
    if os.environ.get("MYRM_BROWSER_ORCHESTRATOR", "").strip() != "1":
        return HotPathDecision(False, "orchestrator_disabled", False)
    if os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip().upper() != "SHARED":
        return HotPathDecision(False, "not_shared", False)
    access_scope = os.environ.get("MYRM_E2E_ACCESS_SCOPE", "").strip().upper()
    if access_scope not in {"READ", "NAMESPACE_WRITE"}:
        return HotPathDecision(False, "not_read_or_namespace_write", False)

    needs_binding = False
    try:
        from cdp_chat.support import get_open_page_api_url

        api_base = get_open_page_api_url().rstrip("/")
        if api_base and api_base != "http://127.0.0.1:8080":
            return HotPathDecision(False, "private_api_base", True)
    except ImportError:
        pass

    try:
        from cdp_chat.support import e2e_runtime_binding_source

        if e2e_runtime_binding_source():
            needs_binding = True
    except ImportError:
        pass

    try:
        from cdp_chat.support import get_e2e_ui_url

        ui_origin = _ui_origin(get_e2e_ui_url())
    except ImportError:
        ui_origin = "http://127.0.0.1:3000"

    parsed = urlsplit(url.strip())
    url_origin = _ui_origin(url)
    if url_origin.rstrip("/") != ui_origin.rstrip("/"):
        return HotPathDecision(False, "off_platform_origin", needs_binding)

    route = _normalize_route(parsed.path or "/")
    shell_route = (
        "/settings"
        if route.startswith("/settings/") and route != "/settings"
        else route
    )
    shell_fresh = platform_shell_fresh(route_path=shell_route)

    if not shell_fresh:
        if not epoch_aligned():
            return HotPathDecision(False, "epoch_drift", needs_binding)
        return HotPathDecision(False, "platform_shell_not_fresh", needs_binding)

    if route.startswith("/settings/") and route != "/settings":
        if epoch_aligned():
            return HotPathDecision(
                True, "shared_read_hot_heavy_settings_warmed", needs_binding
            )
        return HotPathDecision(
            True,
            "shared_read_hot_heavy_settings_warmed_epoch_drift",
            needs_binding,
        )

    if epoch_aligned():
        reason = "shared_read_hot_with_binding" if needs_binding else "shared_read_hot"
        return HotPathDecision(True, reason, needs_binding)
    drift_reason = (
        "shared_read_hot_shell_fresh_epoch_drift_with_binding"
        if needs_binding
        else "shared_read_hot_shell_fresh_epoch_drift"
    )
    return HotPathDecision(True, drift_reason, needs_binding)


def set_bootstrap_hot_path(mode: BootstrapHotPath) -> None:
    os.environ["MYRM_E2E_BOOTSTRAP_HOT_PATH"] = mode
    import sys

    print(f"E2E_BOOTSTRAP_HOT_PATH: mode={mode}", file=sys.stderr, flush=True)
    try:
        from e2e_session_runtime.snapshot import annotate_bootstrap_hot_path

        annotate_bootstrap_hot_path(mode)
    except ImportError:
        pass
