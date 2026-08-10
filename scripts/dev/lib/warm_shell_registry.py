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
import sys
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
    sealed_target_id: str | None = None
    sealed_target_ids: frozenset[str] = frozenset()


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


def _normalize_sealed_target_pool(payload: dict[str, object]) -> list[str]:
    pool: list[str] = []
    seen: set[str] = set()
    ids_raw = payload.get("sealedTargetIds")
    if isinstance(ids_raw, list):
        for item in ids_raw:
            if isinstance(item, str):
                target_id = item.strip()
                if target_id and target_id not in seen:
                    seen.add(target_id)
                    pool.append(target_id)
    legacy_raw = payload.get("sealedTargetId")
    if isinstance(legacy_raw, str):
        legacy_id = legacy_raw.strip()
        if legacy_id and legacy_id not in seen:
            pool.insert(0, legacy_id)
    return pool


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
    pool = _normalize_sealed_target_pool(payload)
    sealed_target_id = pool[0] if pool else None
    return WarmShellRecord(
        workspace_fingerprint=fp,
        ui_origin=ui_origin,
        routes=frozenset(routes),
        sealed_at=float(sealed_raw),
        sealed_target_id=sealed_target_id,
        sealed_target_ids=frozenset(pool),
    )


def seal_platform_shell(
    *,
    ui_url: str,
    route_path: str = "/",
    workspace_fp: str | None = None,
    sealed_target_id: str | None = None,
    append_sealed_target: bool = False,
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
        pool = _normalize_sealed_target_pool(existing_payload)
        effective_target_id = (sealed_target_id or "").strip() or None
        if effective_target_id:
            if append_sealed_target:
                if effective_target_id not in pool:
                    pool.append(effective_target_id)
            else:
                pool = [effective_target_id]
        sealed_at = time.time()
        payload: dict[str, object] = {
            "workspaceFingerprint": fp,
            "uiOrigin": origin,
            "routes": sorted(routes),
            "sealedAt": sealed_at,
        }
        if pool:
            payload["sealedTargetIds"] = pool
            payload["sealedTargetId"] = pool[0]
        record = WarmShellRecord(
            workspace_fingerprint=fp,
            ui_origin=origin,
            routes=frozenset(routes),
            sealed_at=sealed_at,
            sealed_target_id=pool[0] if pool else None,
            sealed_target_ids=frozenset(pool),
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


def count_sealed_target_pool(
    *,
    route_path: str = "/",
    workspace_fp: str | None = None,
) -> int:
    if not platform_shell_fresh(route_path=route_path, workspace_fp=workspace_fp):
        return 0
    record = read_platform_shell(workspace_fp=workspace_fp)
    if record is None:
        return 0
    return len(record.sealed_target_ids)


def seed_sealed_target_pool_via_cdp(
    *,
    ui_url: str,
    need_count: int,
    cdp_port: int = 9333,
    workspace_fp: str | None = None,
    route_path: str = "/",
) -> int:
    """Append background CDP tabs to the warm-shell pool (platform shell must already be hot)."""
    import asyncio
    import importlib.util
    from pathlib import Path

    warmup_path = Path(__file__).with_name("frontend-client-warmup.py")
    lib_dir = str(warmup_path.parent.resolve())
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    module_name = f"_myrm_warmup_seed_{warmup_path.stat().st_mtime_ns}"
    spec = importlib.util.spec_from_file_location(
        module_name,
        warmup_path,
    )
    if spec is None or spec.loader is None:
        return count_sealed_target_pool(
            route_path=route_path, workspace_fp=workspace_fp
        )
    warmup_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(warmup_mod)
    create_background_target = getattr(warmup_mod, "_create_background_target", None)
    wait_for_hydration = getattr(warmup_mod, "_wait_for_hydration", None)
    if create_background_target is None or wait_for_hydration is None:
        return count_sealed_target_pool(
            route_path=route_path, workspace_fp=workspace_fp
        )

    try:
        from infra_browser_registry import register_infra_target
    except ImportError:
        register_infra_target = None  # type: ignore[assignment,misc]

    target_need = max(0, int(need_count))
    if target_need <= 0:
        return count_sealed_target_pool(
            route_path=route_path, workspace_fp=workspace_fp
        )

    seeded = 0
    per_target_timeout = float(
        os.environ.get("MYRM_WARM_SHELL_POOL_SEED_TIMEOUT_SEC", "25") or "25"
    )
    poll_ms = int(os.environ.get("MYRM_WARM_SHELL_POOL_SEED_POLL_MS", "400") or "400")
    async def _seed_one() -> bool:
        target = await create_background_target(cdp_port, initial_url=ui_url)
        target_id = str(target.get("id") or "").strip()
        ws_url = str(target.get("webSocketDebuggerUrl") or "").strip()
        if not target_id or not ws_url:
            return False
        if register_infra_target is not None:
            register_infra_target(target_id, ui_url)
        ready = await wait_for_hydration(
            ws_url,
            ui_url,
            timeout_sec=per_target_timeout,
            poll_ms=poll_ms,
            skip_navigate=False,
        )
        if not ready:
            return False
        record = seal_platform_shell(
            ui_url=ui_url,
            route_path=route_path,
            workspace_fp=workspace_fp,
            sealed_target_id=target_id,
            append_sealed_target=True,
        )
        return record is not None

    for _ in range(target_need):
        try:
            ok = asyncio.run(_seed_one())
        except (OSError, RuntimeError, ValueError):
            ok = False
        if not ok:
            break
        seeded += 1
    return count_sealed_target_pool(route_path=route_path, workspace_fp=workspace_fp)


def ensure_sealed_target_pool(
    *,
    ui_url: str,
    route_path: str = "/",
    min_pool_size: int | None = None,
    workspace_fp: str | None = None,
) -> int:
    """Ensure epoch warm-shell pool has enough CDP tabs for parallel reclaim (§19.13 W3b)."""
    if os.environ.get("MYRM_BROWSER_ORCHESTRATOR", "").strip() != "1":
        return count_sealed_target_pool(
            route_path=route_path, workspace_fp=workspace_fp
        )
    if not platform_shell_fresh(route_path=route_path, workspace_fp=workspace_fp):
        return 0
    need = min_pool_size
    if need is None:
        need = 2
        try:
            from peer_count_ssot import parallel_active_test_count_ssot

            need = max(2, min(4, parallel_active_test_count_ssot()))
        except ImportError:
            pass
    current = count_sealed_target_pool(route_path=route_path, workspace_fp=workspace_fp)
    remaining = max(0, int(need) - current)
    if remaining <= 0:
        return current
    return seed_sealed_target_pool_via_cdp(
        ui_url=ui_url,
        need_count=remaining,
        route_path=route_path,
        workspace_fp=workspace_fp,
    )


def read_sealed_target_id(
    *,
    route_path: str = "/",
    workspace_fp: str | None = None,
) -> str | None:
    """Return first epoch shell targetId when registry entry is fresh for route."""
    if not platform_shell_fresh(route_path=route_path, workspace_fp=workspace_fp):
        return None
    record = read_platform_shell(workspace_fp=workspace_fp)
    if record is None:
        return None
    for target_id in record.sealed_target_ids:
        if target_id.strip():
            return target_id.strip()
    legacy = (record.sealed_target_id or "").strip()
    return legacy or None


def _cdp_page_target_ids(*, cdp_port: int) -> set[str]:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{cdp_port}/json/list",
            timeout=8.0,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return set()
    if not isinstance(payload, list):
        return set()
    alive: set[str] = set()
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "page":
            continue
        target_id = entry.get("id")
        if isinstance(target_id, str) and target_id.strip():
            alive.add(target_id.strip())
    return alive


def _url_path_from_cdp_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    return _normalize_route(parsed.path or "/")


def _cdp_page_target_ids_for_route(*, cdp_port: int, route_path: str = "/") -> set[str]:
    import urllib.error
    import urllib.request

    route = _normalize_route(route_path)
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{cdp_port}/json/list",
            timeout=8.0,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return set()
    if not isinstance(payload, list):
        return set()
    matched: set[str] = set()
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "page":
            continue
        target_id = entry.get("id")
        if not isinstance(target_id, str) or not target_id.strip():
            continue
        if _url_path_from_cdp_url(str(entry.get("url") or "")) != route:
            continue
        matched.add(target_id.strip())
    return matched


def _burst_pool_path(log_dir: str) -> Path:
    return Path(log_dir) / "sealed-pool.json"


def write_burst_sealed_pool(*, log_dir: str, target_ids: list[str]) -> None:
    path = _burst_pool_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"targetIds": [tid.strip() for tid in target_ids if tid.strip()]}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _claim_from_burst_pool(
    *, log_dir: str, cdp_port: int, route_path: str = "/"
) -> str | None:
    path = _burst_pool_path(log_dir)
    if not path.is_file():
        return None
    route_targets = _cdp_page_target_ids_for_route(
        cdp_port=cdp_port, route_path=route_path
    )
    alive_targets = _cdp_page_target_ids(cdp_port=cdp_port)
    with _registry_file_lock(workspace_fp=f"burst-pool-{Path(log_dir).name}"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        pool_raw = payload.get("targetIds")
        if not isinstance(pool_raw, list):
            return None
        pool = [str(item).strip() for item in pool_raw if str(item).strip()]
        claimed: str | None = None
        while pool:
            candidate = pool.pop(0)
            if route_targets and candidate not in route_targets:
                continue
            if alive_targets and candidate not in alive_targets:
                continue
            claimed = candidate
            break
        payload["targetIds"] = pool
        path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return claimed


def claim_sealed_target_id(
    *,
    route_path: str = "/",
    workspace_fp: str | None = None,
    claim_token: str = "",
    cdp_port: int | None = None,
) -> str | None:
    """Atomically claim one sealed shell tab for parallel burst reclaim (§19.11 TAB-6b)."""
    port = int(cdp_port or os.environ.get("MYRM_CHROME_E2E_PORT", "9333") or "9333")
    burst_log_dir = os.environ.get("MYRM_E2E_PHASE_C_LOG_DIR", "").strip()
    if burst_log_dir:
        burst_claimed = _claim_from_burst_pool(
            log_dir=burst_log_dir, cdp_port=port, route_path=route_path
        )
        if burst_claimed:
            return burst_claimed
    resolved_fp = (workspace_fp or current_workspace_fingerprint()).strip()
    if not platform_shell_fresh(
        route_path=route_path,
        workspace_fp=resolved_fp or None,
    ):
        return None
    fp = resolved_fp
    if not fp:
        return None
    path = _registry_path(fp)
    with _registry_file_lock(workspace_fp=fp):
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        pool = _normalize_sealed_target_pool(payload)
        if not pool:
            return None
        alive_targets = _cdp_page_target_ids(cdp_port=port)
        claimed: str | None = None
        while pool:
            candidate = pool.pop(0)
            if alive_targets and candidate not in alive_targets:
                continue
            claimed = candidate
            break
        if claimed is None:
            payload["sealedTargetIds"] = pool
            if pool:
                payload["sealedTargetId"] = pool[0]
            else:
                payload.pop("sealedTargetId", None)
            _write_registry_payload(path, payload)
            return None
        payload["sealedTargetIds"] = pool
        if pool:
            payload["sealedTargetId"] = pool[0]
        else:
            payload.pop("sealedTargetId", None)
        _ = claim_token  # reserved for future claim audit trails
        _write_registry_payload(path, payload)
        return claimed


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
        from cdp_chat_support import get_open_page_api_url

        api_base = get_open_page_api_url().rstrip("/")
        if api_base and api_base != "http://127.0.0.1:8080":
            return HotPathDecision(False, "private_api_base", True)
    except ImportError:
        pass

    try:
        from cdp_chat_support import e2e_runtime_binding_source

        if e2e_runtime_binding_source():
            needs_binding = True
    except ImportError:
        pass

    try:
        from cdp_chat_support import get_e2e_ui_url

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
        from e2e_session_snapshot import annotate_bootstrap_hot_path

        annotate_bootstrap_hot_path(mode)
    except ImportError:
        pass
