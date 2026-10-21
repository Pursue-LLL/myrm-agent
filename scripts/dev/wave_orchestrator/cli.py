"""CLI for wave open/close/status and lease acquire/release/heartbeat.

[INPUT]
- wave_orchestrator.core (POS: wave/lease business logic + stack write gate)

[OUTPUT]
- `./myrm wave` subcommands — JSON stdout, gate exit 3 on deny

[POS]
Maintainer CLI entry for Chrome MCP parallel UI E2E wave orchestration.
"""

from __future__ import annotations

import argparse
import json
import sys

from wave_orchestrator.core import (
    acquire_lease,
    check_stack_write_gate,
    close_wave,
    default_agent_id,
    heartbeat_lease,
    open_wave,
    reap,
    release_lease,
    release_lease_and_close_wave_if_idle,
    wave_status,
)
from wave_orchestrator.lease_cleanup import bind_browser_lease, unbind_browser_lease
from wave_orchestrator.resource_ledger import (
    cleanup_lease_resources,
    cleanup_namespace_resources,
    list_resources,
    register_resource,
)
from wave_orchestrator.types import VALID_LANES, VALID_RESOURCE_KINDS


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def cmd_open(args: argparse.Namespace) -> int:
    try:
        wave = open_wave(agent_id=args.agent, runtime_id=args.runtime_id or None)
    except RuntimeError as exc:
        _fail(str(exc), 2)
    _emit({"ok": True, "wave": wave})
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    try:
        wave = close_wave(force=args.force, agent_id=args.agent)
    except RuntimeError as exc:
        _fail(str(exc), 2)
    _emit({"ok": True, "wave": wave})
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    _emit({"ok": True, **wave_status()})
    return 0


def cmd_reap(_args: argparse.Namespace) -> int:
    summary = reap()
    _emit({"ok": True, "reaped": True, **summary})
    return 0


def cmd_lease_acquire(args: argparse.Namespace) -> int:
    lane = args.lane.upper()
    if lane not in VALID_LANES:
        _fail(f"LEASE_DENIED: invalid lane {args.lane}")
    try:
        lease = acquire_lease(
            lane,
            agent_id=args.agent,
            ttl_sec=args.ttl,
            namespace=args.namespace,
            parent_lease_id=args.parent_lease_id,
        )
    except RuntimeError as exc:
        _fail(str(exc), 2)
    _emit({"ok": True, "lease": lease})
    return 0


def cmd_lease_release(args: argparse.Namespace) -> int:
    try:
        if args.close_wave_if_idle:
            result = release_lease_and_close_wave_if_idle(
                args.lease_id,
                agent_id=args.agent,
            )
        else:
            lease = release_lease(args.lease_id, agent_id=args.agent)
            result = {"lease": lease, "wave": None, "waveClosed": False}
    except RuntimeError as exc:
        _fail(str(exc), 2)
    _emit({"ok": True, **result})
    return 0


def cmd_lease_heartbeat(args: argparse.Namespace) -> int:
    try:
        lease = heartbeat_lease(
            args.lease_id, agent_id=args.agent, extend_sec=args.extend
        )
    except RuntimeError as exc:
        _fail(str(exc), 2)
    _emit({"ok": True, "lease": lease})
    return 0


def cmd_lease_bind_browser(args: argparse.Namespace) -> int:
    try:
        lease = bind_browser_lease(
            args.lease_id,
            page_id=args.page_id,
            target_id=args.target_id,
            context_id=args.context_id,
            agent_id=args.agent,
        )
    except RuntimeError as exc:
        _fail(str(exc), 2)
    _emit({"ok": True, "lease": lease})
    return 0


def cmd_lease_unbind_browser(args: argparse.Namespace) -> int:
    try:
        lease = unbind_browser_lease(args.lease_id, agent_id=args.agent)
    except RuntimeError as exc:
        _fail(str(exc), 2)
    _emit({"ok": True, "lease": lease})
    return 0


def cmd_ledger_register(args: argparse.Namespace) -> int:
    kind = args.kind.lower()
    if kind not in VALID_RESOURCE_KINDS:
        _fail(f"LEDGER_DENIED: invalid kind {args.kind}")
    try:
        record = register_resource(
            args.lease_id,
            kind=kind,  # type: ignore[arg-type]
            ref=args.ref,
            namespace=args.namespace,
            agent_id=args.agent,
        )
    except RuntimeError as exc:
        _fail(str(exc), 2)
    _emit({"ok": True, "resource": record})
    return 0


def cmd_ledger_list(args: argparse.Namespace) -> int:
    resources = list_resources(lease_id=args.lease_id, namespace=args.namespace)
    _emit({"ok": True, "resources": resources, "count": len(resources)})
    return 0


def cmd_ledger_cleanup(args: argparse.Namespace) -> int:
    try:
        if args.lease_id:
            summary = cleanup_lease_resources(args.lease_id)
        elif args.namespace:
            summary = cleanup_namespace_resources(args.namespace)
        else:
            _fail("LEDGER_DENIED: provide --lease-id or --namespace")
    except RuntimeError as exc:
        _fail(str(exc), 2)
    _emit({"ok": True, "cleanup": summary})
    return 0


def cmd_check_stack_write(_args: argparse.Namespace) -> int:
    result = check_stack_write_gate()
    if result["allowed"]:
        print("WAVE_STACK_WRITE_OK")
        return 0
    blockers = result["blockers"]
    stack_pin = result.get("stackPin")
    if stack_pin is not None:
        print(
            "WAVE_STACK_PINNED: open wave pins dev stack — mutation denied",
            file=sys.stderr,
        )
        print(
            f"  wave={stack_pin['waveId']} runtime={stack_pin['runtimeId']} "
            f"openedBy={stack_pin['openedBy']}",
            file=sys.stderr,
        )
    if blockers:
        print(
            "WAVE_STACK_WRITE_DENIED: active leases block reset/restart",
            file=sys.stderr,
        )
        for item in blockers:
            print(
                f"  lease={item['leaseId']} agent={item['agentId']} lane={item['lane']}",
                file=sys.stderr,
            )
    if stack_pin is not None:
        print(
            "WAVE_STACK_PIN_HINT: ./myrm wave close --force or acquire STACK_WRITE lease",
            file=sys.stderr,
        )
    elif blockers:
        print(
            "WAVE_STACK_WRITE_HINT: ./myrm wave close --force or wait for lease TTL",
            file=sys.stderr,
        )
    return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dev test wave orchestrator")
    parser.add_argument(
        "--agent", default=default_agent_id(), help="Agent identity for leases"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    open_p = sub.add_parser("open", help="Open a frozen test wave")
    open_p.add_argument(
        "--runtime-id", default="", help="Freeze explicit runtimeId (default: probe)"
    )
    open_p.set_defaults(handler=cmd_open)

    close_p = sub.add_parser("close", help="Close the active wave")
    close_p.add_argument(
        "--force", action="store_true", help="Release active leases and close"
    )
    close_p.set_defaults(handler=cmd_close)

    status_p = sub.add_parser("status", help="Show wave and lease status")
    status_p.set_defaults(handler=cmd_status)

    reap_p = sub.add_parser(
        "reap", help="Expire stale leases and clean their registered resources"
    )
    reap_p.set_defaults(handler=cmd_reap)

    gate_p = sub.add_parser(
        "check-stack-write", help="Exit 0 when reset/restart is allowed"
    )
    gate_p.set_defaults(handler=cmd_check_stack_write)

    lease_p = sub.add_parser("lease", help="Lease management")
    lease_sub = lease_p.add_subparsers(dest="lease_cmd", required=True)

    acquire_p = lease_sub.add_parser("acquire", help="Acquire a lane lease")
    acquire_p.add_argument(
        "lane",
        help="Lane: READ | RESOURCE_WRITE | GLOBAL_WRITE | LIVE_AGENT | STACK_WRITE",
    )
    acquire_p.add_argument(
        "--namespace", default="", help="RESOURCE_WRITE owner namespace"
    )
    acquire_p.add_argument(
        "--parent-lease-id",
        default="",
        help="Active parent lease for exact session-owned child cleanup",
    )
    acquire_p.add_argument("--ttl", type=int, default=3600, help="Lease TTL seconds")
    acquire_p.set_defaults(handler=cmd_lease_acquire)

    release_p = lease_sub.add_parser("release", help="Release a lease")
    release_p.add_argument("lease_id", help="leaseId to release")
    release_p.add_argument(
        "--close-wave-if-idle",
        action="store_true",
        help="Atomically close the same wave when no active leases remain",
    )
    release_p.set_defaults(handler=cmd_lease_release)

    heartbeat_p = lease_sub.add_parser("heartbeat", help="Extend an active lease TTL")
    heartbeat_p.add_argument("lease_id", help="leaseId to heartbeat")
    heartbeat_p.add_argument(
        "--extend", type=int, default=3600, help="Extend TTL seconds"
    )
    heartbeat_p.set_defaults(handler=cmd_lease_heartbeat)

    bind_p = lease_sub.add_parser("bind-browser", help="Bind an MCP page to a lease")
    bind_p.add_argument("lease_id", help="Active leaseId")
    bind_p.add_argument("page_id", help="pageId returned by Chrome DevTools MCP")
    bind_p.add_argument(
        "--target-id",
        required=True,
        help="Exact CDP targetId for deterministic cleanup",
    )
    bind_p.add_argument(
        "--context-id", default="", help="Optional isolated browser context id"
    )
    bind_p.set_defaults(handler=cmd_lease_bind_browser)

    unbind_p = lease_sub.add_parser(
        "unbind-browser", help="Release page ownership without closing it"
    )
    unbind_p.add_argument("lease_id", help="Active leaseId")
    unbind_p.set_defaults(handler=cmd_lease_unbind_browser)

    ledger_p = sub.add_parser(
        "ledger", help="Resource ledger for resource-owning leases"
    )
    ledger_sub = ledger_p.add_subparsers(dest="ledger_cmd", required=True)

    register_p = ledger_sub.add_parser("register", help="Register a test resource ref")
    register_p.add_argument(
        "lease_id", help="Active RESOURCE_WRITE or GLOBAL_WRITE leaseId"
    )
    register_p.add_argument(
        "kind",
        help="Resource kind: chat | project | agent | cron | file | kanban_board | kanban_task",
    )
    register_p.add_argument("ref", help="Business resource id (e.g. chatId)")
    register_p.add_argument("--namespace", default="", help="Owner namespace override")
    register_p.set_defaults(handler=cmd_ledger_register)

    list_p = ledger_sub.add_parser("list", help="List active ledger resources")
    list_p.add_argument("--lease-id", default="", help="Filter by leaseId")
    list_p.add_argument("--namespace", default="", help="Filter by namespace")
    list_p.set_defaults(handler=cmd_ledger_list)

    cleanup_p = ledger_sub.add_parser("cleanup", help="Cleanup registered resources")
    cleanup_p.add_argument(
        "--lease-id", default="", help="Cleanup resources for leaseId"
    )
    cleanup_p.add_argument(
        "--namespace", default="", help="Cleanup resources for namespace"
    )
    cleanup_p.set_defaults(handler=cmd_ledger_cleanup)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
