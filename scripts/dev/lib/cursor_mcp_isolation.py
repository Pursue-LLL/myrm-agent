"""Cursor Agent MCP isolation contract (§25.8 SSOT).

[INPUT]
- Global and multi-instance Cursor mcp.json paths
- Optional project-level .cursor/mcp.json
- Live daily Chrome DevToolsActivePort / CDP probe

[OUTPUT]
- inspect_mcp_json(): per-file contract verdict
- assert_agent_mcp_contract(): aggregate FAIL/WARN across instances
- probe_daily_chrome_reachable(): live auto-connect prerequisite

[POS]
Harness lib for ./myrm doctor --mcp-isolation and static SSOT tests.
Agent layer only — never checks E2E :9333 mux.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypedDict

ViolationCode = Literal[
    "AGENT_MUX_FORBIDDEN",
    "AGENT_MISSING_AUTO_CONNECT",
    "MCP_JSON_INVALID",
    "MCP_MISSING_CHROME_DEVTOOLS",
    "MCP_FILE_MISSING",
]

Severity = Literal["fail", "warn"]

E2E_CDP_PORT = 9333
FIX_AUTO_CONNECT_HINT = (
    "Set chrome-devtools to: npx -y chrome-devtools-mcp@latest "
    "--auto-connect --no-usage-statistics "
    "(see scripts/dev/CHROME_MCP_E2E.md)"
)


class McpInspection(TypedDict):
    ok: bool
    path: str
    present: bool
    violations: list[str]
    chrome_devtools_command: str | None


class ContractReport(TypedDict):
    ok: bool
    inspections: list[McpInspection]
    violations: list[str]


class ChromeProbe(TypedDict):
    ok: bool
    detail: str
    port: int | None


@dataclass
class DoctorReport:
    contract: ContractReport
    chrome_probe: ChromeProbe | None
    strict_live: bool = False
    ok: bool = field(init=False)

    def __post_init__(self) -> None:
        contract_ok = self.contract["ok"]
        if self.chrome_probe is None:
            probe_ok = True
        elif self.strict_live:
            probe_ok = self.chrome_probe["ok"]
        else:
            probe_ok = True
        self.ok = contract_ok and probe_ok


def _real_home() -> Path:
    override = os.environ.get("CURSOR2_ORIGINAL_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home()


def known_cursor_mcp_paths() -> list[Path]:
    home = _real_home()
    return [
        home / ".cursor" / "mcp.json",
        home / ".cursor2" / ".cursor" / "mcp.json",
        home / ".cursor-3.1.15" / "mcp.json",
    ]


def project_cursor_mcp_paths(start: Path | None = None) -> list[Path]:
    root = start or Path.cwd()
    candidate = root / ".cursor" / "mcp.json"
    return [candidate] if candidate.is_file() else []


def _chrome_devtools_entry(payload: object) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return None
    servers = payload.get("mcpServers")
    if not isinstance(servers, dict):
        return None
    entry = servers.get("chrome-devtools")
    return entry if isinstance(entry, dict) else None


def _command_text(entry: dict[str, object]) -> str:
    command = entry.get("command")
    args = entry.get("args")
    parts: list[str] = []
    if isinstance(command, str) and command.strip():
        parts.append(command.strip())
    if isinstance(args, list):
        for item in args:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
    return " ".join(parts)


def _args_list(entry: dict[str, object]) -> list[str]:
    args = entry.get("args")
    if not isinstance(args, list):
        return []
    return [item.strip() for item in args if isinstance(item, str) and item.strip()]


def _has_auto_connect(entry: dict[str, object]) -> bool:
    command = _command_text(entry)
    if "cdmcp-mux" in command:
        return False
    args = _args_list(entry)
    normalized = {arg.lower().replace("_", "-") for arg in args}
    if "--auto-connect" in normalized or "--autoconnect" in normalized:
        return True
    if any(arg.startswith("--browser-url=") or arg == "--browserUrl" for arg in args):
        return True
    if "--browser-url" in normalized:
        return True
    return "chrome-devtools-mcp" in command and "--auto-connect" in command


def _violation_message(code: ViolationCode, *, path: Path) -> str:
    if code == "AGENT_MUX_FORBIDDEN":
        return (
            f"{path}: chrome-devtools must not use cdmcp-mux in Agent layer — "
            f"{FIX_AUTO_CONNECT_HINT}"
        )
    if code == "AGENT_MISSING_AUTO_CONNECT":
        return (
            f"{path}: chrome-devtools missing --auto-connect (or --browser-url) — "
            f"{FIX_AUTO_CONNECT_HINT}"
        )
    if code == "MCP_JSON_INVALID":
        return f"{path}: invalid JSON"
    if code == "MCP_MISSING_CHROME_DEVTOOLS":
        return f"{path}: missing mcpServers.chrome-devtools entry"
    return f"{path}: missing mcp.json"


def inspect_mcp_json(path: Path) -> McpInspection:
    if not path.is_file():
        return {
            "ok": True,
            "path": str(path),
            "present": False,
            "violations": [],
            "chrome_devtools_command": None,
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "ok": False,
            "path": str(path),
            "present": True,
            "violations": [_violation_message("MCP_JSON_INVALID", path=path)],
            "chrome_devtools_command": None,
        }

    entry = _chrome_devtools_entry(payload)
    if entry is None:
        return {
            "ok": False,
            "path": str(path),
            "present": True,
            "violations": [_violation_message("MCP_MISSING_CHROME_DEVTOOLS", path=path)],
            "chrome_devtools_command": None,
        }

    command = _command_text(entry)
    violations: list[str] = []
    if "cdmcp-mux" in command:
        violations.append(_violation_message("AGENT_MUX_FORBIDDEN", path=path))
    elif not _has_auto_connect(entry):
        violations.append(_violation_message("AGENT_MISSING_AUTO_CONNECT", path=path))

    return {
        "ok": not violations,
        "path": str(path),
        "present": True,
        "violations": violations,
        "chrome_devtools_command": command or None,
    }


def assert_agent_mcp_contract(
    *,
    extra_paths: list[Path] | None = None,
    require_present_paths: bool = False,
) -> ContractReport:
    paths: list[Path] = []
    seen: set[str] = set()
    for candidate in [*known_cursor_mcp_paths(), *(extra_paths or [])]:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        paths.append(candidate)

    inspections: list[McpInspection] = []
    violations: list[str] = []
    for path in paths:
        result = inspect_mcp_json(path)
        inspections.append(result)
        if require_present_paths and not result["present"]:
            msg = _violation_message("MCP_FILE_MISSING", path=path)
            violations.append(msg)
            result = {**result, "ok": False, "violations": [*result["violations"], msg]}
            inspections[-1] = result
        violations.extend(result["violations"])

    return {"ok": not violations, "inspections": inspections, "violations": violations}


def _read_devtools_active_port(port_file: Path) -> int | None:
    if not port_file.is_file():
        return None
    try:
        first_line = port_file.read_text(encoding="utf-8").splitlines()[0].strip()
        port = int(first_line)
    except (OSError, ValueError, IndexError):
        return None
    if port <= 0 or port == E2E_CDP_PORT:
        return None
    return port


def _devtools_active_port_candidates() -> list[int]:
    home = Path.home()
    port_files = [
        home / "Library/Application Support/Google/Chrome/DevToolsActivePort",
        home / "Library/Application Support/Google/Chrome Canary/DevToolsActivePort",
        home / "Library/Application Support/Chromium/DevToolsActivePort",
        home / ".config/google-chrome/DevToolsActivePort",
        home / ".config/chromium/DevToolsActivePort",
    ]
    ports: list[int] = []
    for port_file in port_files:
        port = _read_devtools_active_port(port_file)
        if port is not None:
            ports.append(port)
    if 9222 not in ports:
        ports.append(9222)
    return ports


def _probe_cdp_port(port: int) -> bool:
    for suffix in ("/json/version", "/json/list"):
        url = f"http://127.0.0.1:{port}{suffix}"
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("Browser"):
            return True
        if isinstance(payload, list) and payload:
            return True
    return False


def probe_daily_chrome_reachable() -> ChromeProbe:
    home = Path.home()
    active_port_file = home / "Library/Application Support/Google/Chrome/DevToolsActivePort"
    active_port = _read_devtools_active_port(active_port_file)
    if active_port is not None:
        if _probe_cdp_port(active_port):
            return {
                "ok": True,
                "detail": f"daily Chrome CDP reachable on :{active_port}",
                "port": active_port,
            }
        return {
            "ok": True,
            "detail": (
                f"DevToolsActivePort present (:{active_port}) — "
                "auto-connect profile likely active"
            ),
            "port": active_port,
        }

    for port in _devtools_active_port_candidates():
        if port == E2E_CDP_PORT:
            continue
        if _probe_cdp_port(port):
            return {
                "ok": True,
                "detail": f"daily Chrome CDP reachable on :{port}",
                "port": port,
            }
    return {
        "ok": False,
        "detail": (
            "daily Chrome CDP not reachable — launch Chrome 144+ before using "
            "Cursor browser MCP (--auto-connect)"
        ),
        "port": None,
    }


def build_doctor_report(*, skip_live: bool = False, strict_live: bool = False) -> DoctorReport:
    contract = assert_agent_mcp_contract(
        extra_paths=project_cursor_mcp_paths(),
        require_present_paths=False,
    )
    chrome_probe = None if skip_live else probe_daily_chrome_reachable()
    return DoctorReport(
        contract=contract,
        chrome_probe=chrome_probe,
        strict_live=strict_live,
    )


def _print_doctor_report(report: DoctorReport) -> None:
    print("CURSOR_MCP_ISOLATION_DOCTOR: starting")
    for inspection in report.contract["inspections"]:
        label = inspection["path"]
        if not inspection["present"]:
            print(f"CURSOR_MCP_ISOLATION_SKIP: {label} (absent)")
            continue
        command = inspection["chrome_devtools_command"] or "(missing)"
        status = "OK" if inspection["ok"] else "FAIL"
        print(f"CURSOR_MCP_ISOLATION_{status}: {label}")
        print(f"  chrome-devtools: {command}")
        for violation in inspection["violations"]:
            print(f"  - {violation}", file=sys.stderr)

    if report.chrome_probe is not None:
        if report.chrome_probe["ok"]:
            print(f"CURSOR_MCP_ISOLATION_OK: {report.chrome_probe['detail']}")
        else:
            print(
                f"CURSOR_MCP_ISOLATION_WARN: {report.chrome_probe['detail']}",
                file=sys.stderr,
            )

    if report.ok:
        print("CURSOR_MCP_ISOLATION_DOCTOR: PASS")
    else:
        print("CURSOR_MCP_ISOLATION_DOCTOR: FAIL", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cursor Agent MCP isolation doctor (§25.8)",
    )
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="Skip daily Chrome CDP live probe",
    )
    parser.add_argument(
        "--strict-live",
        action="store_true",
        help="Treat unreachable daily Chrome as FAIL (default WARN only)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON",
    )
    args = parser.parse_args(argv)

    report = build_doctor_report(
        skip_live=args.skip_live,
        strict_live=args.strict_live,
    )
    if args.json:
        payload = {
            "ok": report.ok,
            "contract": report.contract,
            "chrome_probe": report.chrome_probe,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_doctor_report(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
