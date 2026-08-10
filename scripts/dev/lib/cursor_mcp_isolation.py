"""Cursor Agent MCP isolation contract (§25.8 SSOT).

[INPUT]
- Global and multi-instance Cursor mcp.json paths
- Optional project-level .cursor/mcp.json
- Live ChromeAgent pipe-proxy (:9410) health probe

[OUTPUT]
- inspect_mcp_json(): per-file contract verdict
- assert_agent_mcp_contract(): aggregate FAIL/WARN across instances
- probe_chrome_agent_reachable(): live ChromeAgent prerequisite
- probe_chrome_agent_launchagent(): LaunchAgent daemon state
- probe_chrome_agent_focus(): macOS focus theft mechanical check

[POS]
Harness lib for ./myrm doctor --mcp-isolation and static SSOT tests.
Agent layer only — never checks E2E :9333 mux.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypedDict

ViolationCode = Literal[
    "AGENT_MUX_FORBIDDEN",
    "AGENT_E2E_PORT_FORBIDDEN",
    "AGENT_AUTO_CONNECT_FORBIDDEN",
    "AGENT_DAILY_PORT_FORBIDDEN",
    "AGENT_MISSING_CHROME_AGENT",
    "MCP_JSON_INVALID",
    "MCP_MISSING_CHROME_DEVTOOLS",
    "MCP_FILE_MISSING",
]

Severity = Literal["fail", "warn"]

E2E_CDP_PORT = 9333
AGENT_CDP_PORT = 9410
CHROME_AGENT_LAUNCHAGENT_LABEL = "com.myrm.chrome-agent"
CHROME_AGENT_FOCUS_PROBES = 5
FIX_CHROME_AGENT_HINT = (
    "Set chrome-devtools to: npx -y chrome-devtools-mcp@latest "
    f"--browserUrl http://127.0.0.1:{AGENT_CDP_PORT} --no-usage-statistics "
    "(see scripts/dev/CHROME_MCP_E2E.md; run ./myrm ready --chrome-agent)"
)
FIX_AUTO_CONNECT_HINT = FIX_CHROME_AGENT_HINT


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


class LiveProbe(TypedDict):
    ok: bool
    detail: str


@dataclass
class DoctorReport:
    contract: ContractReport
    chrome_probe: ChromeProbe | None
    launchagent_probe: LiveProbe | None
    focus_probe: LiveProbe | None
    strict_live: bool = False
    ok: bool = field(init=False)

    def __post_init__(self) -> None:
        contract_ok = self.contract["ok"]
        live_probes: list[LiveProbe | None] = [
            self.chrome_probe,
            self.launchagent_probe,
            self.focus_probe,
        ]
        if self.strict_live:
            probes_ok = all(p is None or p["ok"] for p in live_probes)
        else:
            probes_ok = True
        self.ok = contract_ok and probes_ok


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


def _entry_env_text(entry: dict[str, object]) -> str:
    env = entry.get("env")
    if not isinstance(env, dict):
        return ""
    parts: list[str] = []
    for key, value in env.items():
        if isinstance(key, str):
            parts.append(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


def _references_e2e_chrome(entry: dict[str, object]) -> bool:
    blob = " ".join((_command_text(entry), _entry_env_text(entry))).lower()
    markers = (
        f":{E2E_CDP_PORT}",
        "127.0.0.1:9333",
        "localhost:9333",
        "myrm_chrome_e2e",
        "chromee2e",
        "cdmcp-mux",
    )
    return any(marker in blob for marker in markers)


def _references_auto_connect(entry: dict[str, object]) -> bool:
    normalized = {arg.lower().replace("_", "-") for arg in _args_list(entry)}
    return "--auto-connect" in normalized or "--autoconnect" in normalized


def _references_daily_cdp_port(entry: dict[str, object]) -> bool:
    blob = " ".join((_command_text(entry), _entry_env_text(entry))).lower()
    daily_markers = (
        ":9222",
        "127.0.0.1:9222",
        "localhost:9222",
    )
    return any(marker in blob for marker in daily_markers)


def _has_chrome_agent_browser_url(entry: dict[str, object]) -> bool:
    blob = " ".join((_command_text(entry), _entry_env_text(entry))).lower()
    agent_markers = (
        f":{AGENT_CDP_PORT}",
        f"127.0.0.1:{AGENT_CDP_PORT}",
        f"localhost:{AGENT_CDP_PORT}",
    )
    return any(marker in blob for marker in agent_markers)


def _violation_message(code: ViolationCode, *, path: Path) -> str:
    if code == "AGENT_MUX_FORBIDDEN":
        return (
            f"{path}: chrome-devtools must not use cdmcp-mux in Agent layer — "
            f"{FIX_CHROME_AGENT_HINT}"
        )
    if code == "AGENT_E2E_PORT_FORBIDDEN":
        return (
            f"{path}: chrome-devtools must not reference E2E :9333 / Myrm ChromeE2E — "
            f"{FIX_CHROME_AGENT_HINT}"
        )
    if code == "AGENT_AUTO_CONNECT_FORBIDDEN":
        return (
            f"{path}: chrome-devtools --auto-connect steals macOS focus — "
            f"{FIX_CHROME_AGENT_HINT}"
        )
    if code == "AGENT_DAILY_PORT_FORBIDDEN":
        return (
            f"{path}: chrome-devtools must not use daily Chrome :9222 — "
            f"{FIX_CHROME_AGENT_HINT}"
        )
    if code == "AGENT_MISSING_CHROME_AGENT":
        return (
            f"{path}: chrome-devtools must use ChromeAgent "
            f"--browserUrl http://127.0.0.1:{AGENT_CDP_PORT} — "
            f"{FIX_CHROME_AGENT_HINT}"
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
            "violations": [
                _violation_message("MCP_MISSING_CHROME_DEVTOOLS", path=path)
            ],
            "chrome_devtools_command": None,
        }

    command = _command_text(entry)
    violations: list[str] = []
    if _references_e2e_chrome(entry):
        if "cdmcp-mux" in command.lower():
            violations.append(_violation_message("AGENT_MUX_FORBIDDEN", path=path))
        else:
            violations.append(_violation_message("AGENT_E2E_PORT_FORBIDDEN", path=path))
    elif _references_auto_connect(entry):
        violations.append(_violation_message("AGENT_AUTO_CONNECT_FORBIDDEN", path=path))
    elif _references_daily_cdp_port(entry):
        violations.append(_violation_message("AGENT_DAILY_PORT_FORBIDDEN", path=path))
    elif not _has_chrome_agent_browser_url(entry):
        violations.append(_violation_message("AGENT_MISSING_CHROME_AGENT", path=path))

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


def _run_osascript(script: str) -> str | None:
    try:
        completed = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    text = completed.stdout.strip()
    return text or None


def probe_chrome_agent_launchagent() -> LiveProbe:
    label = CHROME_AGENT_LAUNCHAGENT_LABEL
    target = f"gui/{os.getuid()}/{label}"
    try:
        completed = subprocess.run(
            ["launchctl", "print", target],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "ok": False,
            "detail": (
                f"LaunchAgent {label} check failed — "
                "run ./myrm ready --chrome-agent --daemon"
            ),
        }
    if completed.returncode != 0:
        return {
            "ok": False,
            "detail": (
                f"LaunchAgent {label} not loaded — "
                "run ./myrm ready --chrome-agent --daemon"
            ),
        }
    if "state = running" not in completed.stdout:
        return {
            "ok": False,
            "detail": f"LaunchAgent {label} loaded but not running",
        }
    return {"ok": True, "detail": f"LaunchAgent {label} running"}


def probe_chrome_agent_focus(*, probes: int = CHROME_AGENT_FOCUS_PROBES) -> LiveProbe:
    chrome_probe = probe_chrome_agent_reachable()
    if not chrome_probe["ok"]:
        return {
            "ok": False,
            "detail": f"focus skipped: {chrome_probe['detail']}",
        }

    _run_osascript('tell application "Cursor" to activate')
    before = _run_osascript(
        'tell application "System Events" to get name of first application process '
        "whose frontmost is true"
    )
    if before is None:
        return {"ok": False, "detail": "focus check failed: could not read frontmost app"}

    for _ in range(max(1, probes)):
        list_url = f"http://127.0.0.1:{AGENT_CDP_PORT}/json/list"
        try:
            with urllib.request.urlopen(list_url, timeout=5) as response:
                response.read()
        except (OSError, urllib.error.URLError):
            return {
                "ok": False,
                "detail": "focus check failed: ChromeAgent /json/list unreachable during probes",
            }

    after = _run_osascript(
        'tell application "System Events" to get name of first application process '
        "whose frontmost is true"
    )
    if after is None:
        return {"ok": False, "detail": "focus check failed: could not read frontmost app after probes"}

    if after == "Google Chrome" and before != "Google Chrome":
        return {
            "ok": False,
            "detail": (
                f"Chrome stole focus ({before} -> {after}) after {probes} CDP probes"
            ),
        }
    return {
        "ok": True,
        "detail": f"focus ok before={before} after={after} probes={probes}",
    }


def probe_chrome_agent_reachable() -> ChromeProbe:
    status_url = f"http://127.0.0.1:{AGENT_CDP_PORT}/proxy/status"
    try:
        with urllib.request.urlopen(status_url, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return {
            "ok": False,
            "detail": (
                f"ChromeAgent pipe-proxy not reachable on :{AGENT_CDP_PORT} — "
                "run ./myrm ready --chrome-agent"
            ),
            "port": None,
        }
    if not isinstance(payload, dict) or not payload.get("chromeRunning"):
        return {
            "ok": False,
            "detail": (
                f"ChromeAgent proxy up but Chrome not running on :{AGENT_CDP_PORT} — "
                "see ~/.local/state/myrm-dev/chrome-agent-proxy.log"
            ),
            "port": AGENT_CDP_PORT,
        }
    return {
        "ok": True,
        "detail": (
            f"ChromeAgent pipe-proxy healthy on :{AGENT_CDP_PORT} "
            f"(clients={payload.get('clients', 0)})"
        ),
        "port": AGENT_CDP_PORT,
    }


def build_doctor_report(
    *, skip_live: bool = False, strict_live: bool = False
) -> DoctorReport:
    contract = assert_agent_mcp_contract(
        extra_paths=project_cursor_mcp_paths(),
        require_present_paths=False,
    )
    chrome_probe = None if skip_live else probe_chrome_agent_reachable()
    launchagent_probe = None if skip_live else probe_chrome_agent_launchagent()
    focus_probe = None if skip_live else probe_chrome_agent_focus()
    return DoctorReport(
        contract=contract,
        chrome_probe=chrome_probe,
        launchagent_probe=launchagent_probe,
        focus_probe=focus_probe,
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
            level = "FAIL" if report.strict_live else "WARN"
            print(
                f"CURSOR_MCP_ISOLATION_{level}: {report.chrome_probe['detail']}",
                file=sys.stderr,
            )

    for probe_name, probe in (
        ("LAUNCHAGENT", report.launchagent_probe),
        ("FOCUS", report.focus_probe),
    ):
        if probe is None:
            continue
        if probe["ok"]:
            print(f"CURSOR_MCP_ISOLATION_OK: {probe_name} {probe['detail']}")
        else:
            level = "FAIL" if report.strict_live else "WARN"
            print(
                f"CURSOR_MCP_ISOLATION_{level}: {probe_name} {probe['detail']}",
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
        help="Skip ChromeAgent pipe-proxy live probe",
    )
    parser.add_argument(
        "--strict-live",
        action="store_true",
        help="Treat live probe failures (proxy, LaunchAgent, focus) as FAIL",
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
            "launchagent_probe": report.launchagent_probe,
            "focus_probe": report.focus_probe,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_doctor_report(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
