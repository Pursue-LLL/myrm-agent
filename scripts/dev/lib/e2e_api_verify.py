"""Resolve the correct dev API base for Agent/server verification during parallel E2E.

Verification Plane SSOT: route API checks to a backend whose stored stack-epoch
source_fingerprint matches the workspace fingerprint. Fail-closed when no match.

[INPUT]
- runtime_identity._backend_source_fingerprint (workspace FP SSOT)
- isolated_runtime_registry (private backend ports + stateDir)
- stack-epoch.json per backend state dir (stored FP SSOT)
- stack_mutation_policy (pending drift, active lease count)

[OUTPUT]
- resolve_e2e_api_context / resolve_verify_api_base
- CLI: context-json, verify-api (proxy curl; optional --ensure-backend seed)

[POS]
Agent-facing SSOT for API verification — eliminates stale :8080 / stale private pool false results.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from runtime_identity import _backend_source_fingerprint
from stack_mutation_policy import (
    _default_state_dir,
    apply_pending_drift_if_idle,
    decide_drift_heal,
    pending_drift_exists,
    read_pending_drift,
    wave_active_lease_count,
)

SHARED_DEFAULT_PORT: Final[int] = 8080
PRIVATE_PORT_SCAN_START: Final[int] = 18080
PRIVATE_PORT_SCAN_END: Final[int] = 18120
HEALTH_PATHS: Final[tuple[str, ...]] = ("/api/v1/health", "/health")
HEALTH_PROBE_TIMEOUT_SEC: Final[float] = 2.0
PORT_SCAN_PROBE_TIMEOUT_SEC: Final[float] = 0.5


@dataclass(frozen=True, slots=True)
class BackendCandidate:
    api_base: str
    port: int
    source: str
    state_dir: str
    stored_fingerprint: str
    workspace_fingerprint: str
    epoch_match: bool
    health_ok: bool
    epoch: int | None


@dataclass(frozen=True, slots=True)
class E2eApiContext:
    verify_api_base: str
    shared_api_base: str
    workspace_fingerprint: str
    epoch_match: bool
    drift_pending: bool
    active_leases: int
    drift_action: str
    source: str
    agent_rule: str
    blocked: bool
    blocked_reason: str
    candidates: tuple[BackendCandidate, ...]


def monorepo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def shared_api_base() -> str:
    explicit = os.environ.get("MYRM_SHARED_E2E_API_BASE", "").strip()
    if explicit:
        return explicit.rstrip("/")
    port_raw = os.environ.get("MYRM_BACKEND_PORT", str(SHARED_DEFAULT_PORT)).strip()
    port = int(port_raw) if port_raw.isdigit() else SHARED_DEFAULT_PORT
    return f"http://127.0.0.1:{port}"


def shared_dev_state_dir() -> Path:
    override = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
    if override:
        return Path(override).resolve()
    return Path.home() / ".local/state/myrm-dev"


def isolated_registry_root() -> Path:
    override = os.environ.get("MYRM_ISOLATED_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return Path.home() / ".local/state/myrm-isolated"


def workspace_backend_fingerprint() -> str:
    return _backend_source_fingerprint()


def _scripts_dev_dir() -> Path:
    return monorepo_root() / "scripts" / "dev"


def _ensure_scripts_dev_importable() -> None:
    dev_dir = str(_scripts_dev_dir())
    if dev_dir not in sys.path:
        sys.path.insert(0, dev_dir)


def _read_stored_epoch(state_dir: Path) -> tuple[int | None, str]:
    epoch_file = state_dir / "stack-epoch.json"
    if not epoch_file.is_file():
        return None, ""
    try:
        raw = json.loads(epoch_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, ""
    if not isinstance(raw, dict):
        return None, ""
    epoch_raw = raw.get("epoch")
    epoch = epoch_raw if isinstance(epoch_raw, int) and epoch_raw >= 1 else None
    stored_fp = raw.get("source_fingerprint")
    if not isinstance(stored_fp, str):
        stored_fp = ""
    return epoch, stored_fp.strip()


def _api_health_ok(api_base: str, timeout_sec: float = HEALTH_PROBE_TIMEOUT_SEC) -> bool:
    base = api_base.rstrip("/")
    for path in HEALTH_PATHS:
        url = f"{base}{path}"
        try:
            with urllib.request.urlopen(url, timeout=timeout_sec) as resp:  # noqa: S310
                if 200 <= resp.status < 300:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return False


def _read_health_stack_epoch(api_base: str) -> tuple[int | None, str]:
    url = f"{api_base.rstrip('/')}/api/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=HEALTH_PROBE_TIMEOUT_SEC) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None, ""
    if not isinstance(payload, dict):
        return None, ""
    stack_epoch = payload.get("stack_epoch")
    if not isinstance(stack_epoch, dict):
        return None, ""
    epoch_raw = stack_epoch.get("epoch")
    epoch = epoch_raw if isinstance(epoch_raw, int) and epoch_raw >= 1 else None
    stored_fp = stack_epoch.get("source_fingerprint")
    if not isinstance(stored_fp, str):
        stored_fp = ""
    return epoch, stored_fp.strip()


def _resolve_candidate_fingerprint(
    *,
    api_base: str,
    state_dir: Path,
    health_ok: bool,
) -> tuple[int | None, str]:
    epoch, stored_fp = _read_stored_epoch(state_dir)
    if stored_fp:
        return epoch, stored_fp
    if health_ok:
        return _read_health_stack_epoch(api_base)
    return epoch, stored_fp


def _epoch_matches(*, stored_fp: str, workspace_fp: str) -> bool:
    if not workspace_fp:
        return False
    if not stored_fp:
        return False
    return stored_fp == workspace_fp


def _port_from_api_base(api_base: str) -> int:
    explicit = os.environ.get("MYRM_BACKEND_PORT", "").strip()
    if api_base.rstrip("/").endswith(f":{SHARED_DEFAULT_PORT}") and explicit.isdigit():
        return int(explicit)
    tail = api_base.rsplit(":", 1)[-1]
    if tail.isdigit():
        return int(tail)
    return SHARED_DEFAULT_PORT


def _enumerate_registry_candidates() -> list[tuple[str, int, str, str]]:
    _ensure_scripts_dev_importable()
    from isolated_runtime_registry import ACTIVE_PHASES, read_registry  # noqa: PLC0415

    registry_path = isolated_registry_root() / "registry.json"
    if not registry_path.is_file():
        return []
    try:
        records = read_registry(registry_path)
    except RuntimeError:
        return []
    found: list[tuple[str, int, str, str]] = []
    for record in records.values():
        if record["phase"] not in ACTIVE_PHASES:
            continue
        port = record["backendPort"]
        state_dir = record["stateDir"]
        api_base = f"http://127.0.0.1:{port}"
        found.append((api_base, port, state_dir, "isolated_registry"))
    return sorted(found, key=lambda item: item[1])


def _enumerate_port_scan_candidates(
    known_ports: set[int],
) -> list[tuple[str, int, str, str]]:
    found: list[tuple[str, int, str, str]] = []
    for port in range(PRIVATE_PORT_SCAN_START, PRIVATE_PORT_SCAN_END + 1):
        if port in known_ports:
            continue
        api_base = f"http://127.0.0.1:{port}"
        if _api_health_ok(api_base, timeout_sec=PORT_SCAN_PROBE_TIMEOUT_SEC):
            found.append((api_base, port, "", "port_scan"))
    return found


def _build_candidates_from_specs(
    specs: list[tuple[str, int, str, str]],
    *,
    workspace_fp: str,
) -> list[BackendCandidate]:
    candidates: list[BackendCandidate] = []
    for api_base, port, state_dir_raw, source in specs:
        state_dir = Path(state_dir_raw) if state_dir_raw else Path()
        health_ok = _api_health_ok(api_base)
        epoch, stored_fp = _resolve_candidate_fingerprint(
            api_base=api_base,
            state_dir=state_dir,
            health_ok=health_ok,
        )
        epoch_match = _epoch_matches(stored_fp=stored_fp, workspace_fp=workspace_fp)
        candidates.append(
            BackendCandidate(
                api_base=api_base.rstrip("/"),
                port=port,
                source=source,
                state_dir=state_dir_raw,
                stored_fingerprint=stored_fp,
                workspace_fingerprint=workspace_fp,
                epoch_match=epoch_match,
                health_ok=health_ok,
                epoch=epoch,
            )
        )
    return candidates


def enumerate_backend_candidates(*, workspace_fp: str) -> list[BackendCandidate]:
    specs: list[tuple[str, int, str, str]] = []
    shared = shared_api_base()
    shared_port = _port_from_api_base(shared)
    specs.append((shared, shared_port, str(shared_dev_state_dir()), "shared"))
    specs.extend(_enumerate_registry_candidates())

    candidates = _build_candidates_from_specs(specs, workspace_fp=workspace_fp)
    if any(item.epoch_match and item.health_ok for item in candidates):
        return candidates

    known_ports = {port for _, port, _, _ in specs}
    specs.extend(_enumerate_port_scan_candidates(known_ports))
    return _build_candidates_from_specs(specs, workspace_fp=workspace_fp)


def _select_verify_candidate(
    candidates: list[BackendCandidate],
    *,
    active_leases: int,
) -> BackendCandidate | None:
    matching = [item for item in candidates if item.epoch_match and item.health_ok]
    if not matching:
        return None

    def sort_key(item: BackendCandidate) -> tuple[int, int, int]:
        private_bias = 0 if item.source != "shared" else 1
        lease_private_bias = private_bias if active_leases > 0 else 0
        epoch_rank = item.epoch if item.epoch is not None else 0
        return (lease_private_bias, -epoch_rank, item.port)

    return sorted(matching, key=sort_key)[0]


def _blocked_reason(
    *,
    candidates: list[BackendCandidate],
    active_leases: int,
    drift_pending: bool,
    workspace_fp: str,
) -> str:
    healthy = [item for item in candidates if item.health_ok]
    if not workspace_fp:
        return "workspace backend source_fingerprint unavailable"
    if not healthy:
        return "no healthy backend reachable; run ./myrm ready --attach"
    stale = [item for item in healthy if not item.epoch_match]
    if stale and active_leases > 0:
        return (
            f"no backend at workspace epoch ({active_leases} active leases; "
            "SMP may defer shared reload)"
        )
    if stale and drift_pending:
        return "pending stack drift; no private backend at workspace epoch"
    if stale:
        return "all healthy backends run stale code; run ./myrm restart --backend"
    return "no verify target selected"


def _build_context_from_resolution(
    *,
    verify: BackendCandidate | None,
    candidates: list[BackendCandidate],
    shared: str,
    workspace_fp: str,
    drift_pending: bool,
    active_leases: int,
    drift_action: str,
) -> E2eApiContext:
    if verify is not None:
        rule = (
            "verify-api routed to epoch-matched backend; "
            "do not curl shared :8080; "
            "do not use Chrome Settings UI to verify new server logic during drift "
            "(shared :3000 always proxies :8080)"
        )
        return E2eApiContext(
            verify_api_base=verify.api_base,
            shared_api_base=shared.rstrip("/"),
            workspace_fingerprint=workspace_fp,
            epoch_match=True,
            drift_pending=drift_pending,
            active_leases=active_leases,
            drift_action=drift_action,
            source=verify.source,
            agent_rule=rule,
            blocked=False,
            blocked_reason="",
            candidates=tuple(candidates),
        )

    blocked_reason = _blocked_reason(
        candidates=candidates,
        active_leases=active_leases,
        drift_pending=drift_pending,
        workspace_fp=workspace_fp,
    )
    fallback_base = shared.rstrip("/")
    for item in candidates:
        if item.source == "shared" and item.health_ok:
            fallback_base = item.api_base
            break
    rule = (
        f"BLOCKED: {blocked_reason}. "
        "Use verify-api only; do not curl shared :8080; do not stop other tests."
    )
    return E2eApiContext(
        verify_api_base=fallback_base,
        shared_api_base=shared.rstrip("/"),
        workspace_fingerprint=workspace_fp,
        epoch_match=False,
        drift_pending=drift_pending,
        active_leases=active_leases,
        drift_action=drift_action,
        source="blocked",
        agent_rule=rule,
        blocked=True,
        blocked_reason=blocked_reason,
        candidates=tuple(candidates),
    )


def resolve_e2e_api_context(
    *,
    monorepo: Path | None = None,
    state_dir: Path | None = None,
    retry_after_apply: bool = True,
) -> E2eApiContext:
    root = (monorepo or monorepo_root()).resolve()
    resolved_state = state_dir or _default_state_dir()
    shared = shared_api_base()
    workspace_fp = workspace_backend_fingerprint()

    if pending_drift_exists(resolved_state) and wave_active_lease_count(root) == 0:
        apply_pending_drift_if_idle(monorepo_root=root, state_dir=resolved_state)

    drift_pending = pending_drift_exists(resolved_state)
    active_leases = wave_active_lease_count(root)
    drift_action = decide_drift_heal(
        active_leases=active_leases,
        drift_pending=drift_pending,
    ).value

    candidates = enumerate_backend_candidates(workspace_fp=workspace_fp)
    verify = _select_verify_candidate(candidates, active_leases=active_leases)

    if verify is None and retry_after_apply and active_leases == 0 and drift_pending:
        apply_result = apply_pending_drift_if_idle(monorepo_root=root, state_dir=resolved_state)
        if apply_result.action == "applied":
            drift_pending = pending_drift_exists(resolved_state)
            drift_action = decide_drift_heal(
                active_leases=active_leases,
                drift_pending=drift_pending,
            ).value
            candidates = enumerate_backend_candidates(workspace_fp=workspace_fp)
            verify = _select_verify_candidate(candidates, active_leases=active_leases)

    pending = read_pending_drift(resolved_state)
    if pending is not None and drift_pending:
        _ = pending.reason

    return _build_context_from_resolution(
        verify=verify,
        candidates=candidates,
        shared=shared,
        workspace_fp=workspace_fp,
        drift_pending=drift_pending,
        active_leases=active_leases,
        drift_action=drift_action,
    )


def resolve_verify_api_base() -> str:
    ctx = resolve_e2e_api_context()
    if ctx.blocked:
        return ctx.shared_api_base
    return ctx.verify_api_base


def _candidate_to_dict(candidate: BackendCandidate) -> dict[str, object]:
    return asdict(candidate)


def _context_to_dict(ctx: E2eApiContext) -> dict[str, object]:
    payload = asdict(ctx)
    payload["candidates"] = [_candidate_to_dict(item) for item in ctx.candidates]
    payload["verifyTarget"] = ctx.verify_api_base
    return payload


def _cmd_context_json(_args: argparse.Namespace) -> int:
    ctx = resolve_e2e_api_context()
    sys.stdout.write(json.dumps(_context_to_dict(ctx), indent=2, sort_keys=True) + "\n")
    return 0


def _cmd_context_human(_args: argparse.Namespace) -> int:
    ctx = resolve_e2e_api_context()
    drift_note = "yes" if ctx.drift_pending else "no"
    match_note = "yes" if ctx.epoch_match else "no"
    sys.stdout.write(
        "E2E_VERIFY_API="
        f"{ctx.verify_api_base} "
        f"(shared={ctx.shared_api_base} drift_pending={drift_note} "
        f"epoch_match={match_note} leases={ctx.active_leases} source={ctx.source} "
        f"blocked={'yes' if ctx.blocked else 'no'})\n"
    )
    sys.stdout.write(f"WORKSPACE_FINGERPRINT={ctx.workspace_fingerprint}\n")
    if ctx.blocked:
        sys.stdout.write(f"BLOCKED_REASON={ctx.blocked_reason}\n")
    sys.stdout.write(f"AGENT_RULE={ctx.agent_rule}\n")
    return 0


def _cmd_verify_api(args: argparse.Namespace) -> int:
    ctx = resolve_e2e_api_context(
        retry_after_apply=not bool(getattr(args, "ensure_backend", False))
    )
    if ctx.blocked and bool(getattr(args, "ensure_backend", False)):
        from verify_backend_seed import ensure_verify_backend_seed  # noqa: PLC0415

        seed = ensure_verify_backend_seed(monorepo=monorepo_root())
        sys.stderr.write(
            f"MYRM_VERIFY_API_SEED: ok={seed.ok} runtime={seed.runtime_id} "
            f"api={seed.api_base} detail={seed.detail}\n"
        )
        if seed.ok:
            ctx = resolve_e2e_api_context(retry_after_apply=False)
    if ctx.blocked:
        sys.stderr.write(f"MYRM_VERIFY_API_BLOCKED: {ctx.blocked_reason}\n")
        sys.stderr.write(f"AGENT_RULE={ctx.agent_rule}\n")
        sys.stderr.write(
            "Hint: parallel leases defer shared reload; seed a private backend via "
            "SHPOIB pytest or wait for auto drift heal when leases finish.\n"
        )
        return 2
    method = str(args.method).upper()
    path = str(args.path)
    if not path.startswith("/"):
        path = f"/{path}"
    url = f"{ctx.verify_api_base.rstrip('/')}{path}"
    sys.stderr.write(
        f"MYRM_VERIFY_API: {method} {url} "
        f"(shared={ctx.shared_api_base} drift_pending={ctx.drift_pending} "
        f"epoch_match={ctx.epoch_match} leases={ctx.active_leases} source={ctx.source})\n"
    )
    curl_cmd: list[str] = [
        "curl",
        "-sS",
        "-w",
        "\nHTTP:%{http_code}\n",
        "-X",
        method,
        url,
    ]
    if args.data is not None:
        curl_cmd.extend(["-H", "Content-Type: application/json", "-d", args.data])
    proc = subprocess.run(curl_cmd, check=False)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ctx_json = sub.add_parser("context-json")
    ctx_json.set_defaults(handler=_cmd_context_json)

    ctx_human = sub.add_parser("context-human")
    ctx_human.set_defaults(handler=_cmd_context_human)

    verify = sub.add_parser("verify-api")
    verify.add_argument("method", choices=("GET", "POST", "PUT", "PATCH", "DELETE"))
    verify.add_argument("path")
    verify.add_argument("data", nargs="?", default=None)
    verify.add_argument(
        "--ensure-backend",
        action="store_true",
        help="When BLOCKED, seed one backend-only isolated runtime (SHPOIB cap)",
    )
    verify.set_defaults(handler=_cmd_verify_api)

    ns = parser.parse_args(argv)
    handler = getattr(ns, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(ns))


if __name__ == "__main__":
    raise SystemExit(main())
