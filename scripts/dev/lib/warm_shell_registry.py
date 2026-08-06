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

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
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
        str(Path.home() / ".local" / "state" / "myrm-e2e"),
    )
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _registry_path(workspace_fp: str) -> Path:
    safe = workspace_fp.strip().replace("/", "_") or "unknown"
    return _state_dir() / _REGISTRY_DIR_NAME / f"{safe}.json"


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
    try:
        from e2e_api_verify import resolve_e2e_api_context

        ctx = resolve_e2e_api_context()
        return str(getattr(ctx, "workspace_fingerprint", "") or "").strip()
    except ImportError:
        return ""


def epoch_aligned() -> bool:
    try:
        from e2e_api_verify import resolve_e2e_api_context

        ctx = resolve_e2e_api_context()
        return bool(getattr(ctx, "epoch_match", False))
    except ImportError:
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
    existing = read_platform_shell(workspace_fp=fp)
    routes = set(existing.routes) if existing is not None else set()
    routes.add(route)
    record = WarmShellRecord(
        workspace_fingerprint=fp,
        ui_origin=origin,
        routes=frozenset(routes),
        sealed_at=time.time(),
    )
    path = _registry_path(fp)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "workspaceFingerprint": fp,
                "uiOrigin": origin,
                "routes": sorted(routes),
                "sealedAt": record.sealed_at,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
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
    if os.environ.get("MYRM_E2E_ACCESS_SCOPE", "").strip().upper() != "READ":
        return HotPathDecision(False, "not_read", False)

    in_e2e_runtime = bool(
        os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
        or os.environ.get("MYRM_E2E_RUN_ID", "").strip()
        or os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
    )
    if in_e2e_runtime:
        try:
            from peer_count_ssot import parallel_active_test_count_ssot

            if parallel_active_test_count_ssot() > 1:
                return HotPathDecision(False, "parallel_peers_active", False)
        except ImportError:
            pass

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
            return HotPathDecision(False, "runtime_binding", True)
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
    if not platform_shell_fresh(route_path=route):
        if not epoch_aligned():
            return HotPathDecision(False, "epoch_drift", needs_binding)
        return HotPathDecision(False, "platform_shell_not_fresh", needs_binding)

    if epoch_aligned():
        return HotPathDecision(True, "shared_read_hot", needs_binding)
    # Parallel SMP may defer shared backend reload while warm_ui_route already sealed
    # this READ route — fast_create avoids cold openPageTransaction queue storms.
    return HotPathDecision(True, "shared_read_hot_shell_fresh_epoch_drift", needs_binding)


def set_bootstrap_hot_path(mode: BootstrapHotPath) -> None:
    os.environ["MYRM_E2E_BOOTSTRAP_HOT_PATH"] = mode
    try:
        from e2e_session_snapshot import annotate_bootstrap_hot_path

        annotate_bootstrap_hot_path(mode)
    except ImportError:
        pass
