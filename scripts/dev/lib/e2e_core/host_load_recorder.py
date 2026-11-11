"""Host load recorder — daemon loop, LaunchAgent lifecycle and CLI.

[INPUT]
- host_load_sampler.LoadSampler (one aggregate sample per tick)
- host_load_store (daily JSONL files under dev_state_dir)

[OUTPUT]
- ``run``: sample every SAMPLE_INTERVAL_SEC until stopped (the LaunchAgent entry point)
- ``summary`` / ``status``: read-only views over recorded data
- ``install`` / ``uninstall``: manage ~/Library/LaunchAgents/com.myrm.host-load-recorder.plist

[POS]
Evidence source for deciding when to admit another heavy dev stack. Runs at default
priority on purpose: a background QoS class is starved exactly when the machine saturates,
which would drop the samples that matter most.

Usage (PYTHONPATH must contain the ``lib`` directory)::

    python -m e2e_core.host_load_recorder install|uninstall|status|summary|run
"""

from __future__ import annotations

import argparse
import logging
import os
import plistlib
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Final, Protocol

from e2e_core.bootstrap_deadline import dev_state_dir
from e2e_core.host_load_report import render_summary
from e2e_core.host_load_sampler import LoadSample, LoadSampler
from e2e_core.host_load_store import (
    FILE_PREFIX,
    append_sample,
    prune_expired,
    read_window,
)
from e2e_core.real_user_home import real_user_home

LAUNCH_LABEL: Final = "com.myrm.host-load-recorder"
SAMPLE_INTERVAL_SEC: Final = 30.0
_LOG_NAME: Final = "host-load-recorder.log"
_LAUNCHCTL: Final = "/bin/launchctl"
_RESTART_THROTTLE_SEC: Final = 60
_MODULE: Final = "e2e_core.host_load_recorder"

logger = logging.getLogger(__name__)


class SampleSource(Protocol):
    def sample(self) -> LoadSample | None: ...


def record_once(sampler: SampleSource, directory: Path) -> bool:
    """Take one sample and append it; False when nothing was written."""
    try:
        sample = sampler.sample()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        logger.warning("Load sample skipped: %s", exc)
        return False
    if sample is None:
        return False
    try:
        append_sample(directory, sample)
    except OSError as exc:
        logger.warning("Load sample not stored: %s", exc)
        return False
    return True


def run_forever(
    interval_sec: float,
    directory: Path,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    sampler = LoadSampler()
    pruned_on: date | None = None
    while True:
        started = time.monotonic()
        record_once(sampler, directory)
        today = date.today()
        if pruned_on != today:
            try:
                prune_expired(directory, today=today)
            except OSError as exc:
                logger.warning("Retention prune failed: %s", exc)
            pruned_on = today
        sleep(max(1.0, interval_sec - (time.monotonic() - started)))


def launch_agent_path() -> Path:
    return real_user_home() / "Library/LaunchAgents" / f"{LAUNCH_LABEL}.plist"


def resolve_interpreter() -> Path:
    """Base interpreter of the running Python, so deleting a project venv cannot break the agent."""
    version = sys.version_info
    base = Path(sys.base_prefix) / "bin" / f"python{version.major}.{version.minor}"
    return base if base.is_file() else Path(sys.executable)


def build_launch_agent(
    *, interpreter: Path, lib_dir: Path, log_path: Path
) -> dict[str, object]:
    return {
        "Label": LAUNCH_LABEL,
        "ProgramArguments": [str(interpreter), "-m", _MODULE, "run"],
        "EnvironmentVariables": {"PYTHONPATH": str(lib_dir)},
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": _RESTART_THROTTLE_SEC,
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(log_path),
    }


def _launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_LAUNCHCTL, *args], capture_output=True, text=True, check=False
    )


def install() -> int:
    if sys.platform != "darwin":
        print("install requires macOS (launchd)", file=sys.stderr)
        return 2
    directory = dev_state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / _LOG_NAME
    log_path.write_text("", encoding="utf-8")
    plist_path = launch_agent_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    agent = build_launch_agent(
        interpreter=resolve_interpreter(),
        lib_dir=Path(__file__).resolve().parents[1],
        log_path=log_path,
    )
    plist_path.write_bytes(plistlib.dumps(agent))
    service = f"gui/{os.getuid()}/{LAUNCH_LABEL}"
    _launchctl("bootout", service)
    result = _launchctl("bootstrap", f"gui/{os.getuid()}", str(plist_path))
    if result.returncode != 0:
        print(f"launchctl bootstrap failed: {result.stderr.strip()}", file=sys.stderr)
        return 1
    _launchctl("enable", service)
    print(
        f"Installed {LAUNCH_LABEL}: sampling every {SAMPLE_INTERVAL_SEC:g}s into {directory}"
    )
    return 0


def uninstall() -> int:
    _launchctl("bootout", f"gui/{os.getuid()}/{LAUNCH_LABEL}")
    launch_agent_path().unlink(missing_ok=True)
    print(f"Uninstalled {LAUNCH_LABEL}; recorded samples were kept")
    return 0


def status() -> int:
    loaded = _launchctl("print", f"gui/{os.getuid()}/{LAUNCH_LABEL}").returncode == 0
    lines = [f"LaunchAgent loaded: {'yes' if loaded else 'no'}"]
    plist_path = launch_agent_path()
    if plist_path.is_file():
        interpreter = Path(
            str(plistlib.loads(plist_path.read_bytes())["ProgramArguments"][0])
        )
        verdict = "ok" if interpreter.is_file() else "MISSING - re-run install"
        lines.append(f"Interpreter: {interpreter} ({verdict})")
    files = sorted(dev_state_dir().glob(f"{FILE_PREFIX}*.jsonl"))
    if files:
        age = time.time() - files[-1].stat().st_mtime
        lines.append(f"Newest data: {files[-1].name}, updated {age:.0f}s ago")
    else:
        lines.append("No data files yet")
    log_path = dev_state_dir() / _LOG_NAME
    if log_path.is_file() and log_path.stat().st_size > 0:
        lines.append(
            f"Log: {log_path.stat().st_size} bytes at {log_path} (recorder errors land here)"
        )
    print("\n".join(lines))
    return 0 if loaded else 1


def summary(hours: float, peaks: int) -> int:
    samples = read_window(dev_state_dir(), since=time.time() - hours * 3600)
    print(render_summary(samples, hours=hours, peaks=peaks))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_MODULE, description="Record and summarize host load."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run", help="sample until stopped (LaunchAgent entry point)"
    )
    run.add_argument(
        "--interval", type=float, default=SAMPLE_INTERVAL_SEC, help="seconds per sample"
    )
    report = commands.add_parser("summary", help="summarize recorded load")
    report.add_argument("--hours", type=float, default=24.0)
    report.add_argument("--peaks", type=int, default=5)
    commands.add_parser("install", help="install and start the LaunchAgent")
    commands.add_parser(
        "uninstall", help="stop and remove the LaunchAgent (data is kept)"
    )
    commands.add_parser("status", help="show LaunchAgent and data freshness")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "run":
        logging.basicConfig(
            level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s"
        )
        run_forever(args.interval, dev_state_dir())
        return 0
    if args.command == "summary":
        return summary(args.hours, args.peaks)
    handlers: dict[str, Callable[[], int]] = {
        "install": install,
        "uninstall": uninstall,
        "status": status,
    }
    return handlers[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
