"""Run probe.py in fresh child processes against the backend's own virtualenv.

[INPUT]
  The backend checkout (myrm-agent-server/.venv), a sample count, optional module stubs
  startup_budget.probe::SAMPLE_PREFIX (POS: child process; one cold measurement of the real
  backend, run here as a subprocess)
  startup_budget.budget::Sample (POS: pure policy; one measurement and how samples are judged)

[OUTPUT]
  list[Sample]; ProbeError when no trustworthy sample could be taken

[POS]
  Process boundary of the startup budget gate. Every sample is a cold interpreter (import cost
  is paid once per process) on a throwaway data directory, so nothing here can touch real user
  data and samples cannot warm each other up.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from startup_budget.budget import Sample
from startup_budget.probe import SAMPLE_PREFIX

SERVER_DIR = Path(__file__).resolve().parents[4] / "myrm-agent-server"
PROBE = Path(__file__).with_name("probe.py")
SERVER_PYTHON_ENV = "MYRM_SERVER_PYTHON"
# One cold sample takes ~15 s on an idle machine and ~60-100 s on an oversubscribed one.
SAMPLE_TIMEOUT_SEC = 480


class ProbeError(RuntimeError):
    """The probe could not produce a sample (broken backend, missing venv, timeout)."""


def server_python() -> Path:
    override = os.environ.get(SERVER_PYTHON_ENV)
    if override:
        return Path(override)
    venv = SERVER_DIR / ".venv"
    return (
        venv / "Scripts" / "python.exe" if os.name == "nt" else venv / "bin" / "python"
    )


def _optional_float(value: float | None) -> float | None:
    return None if value is None else float(value)


def parse_sample(stdout: str) -> Sample:
    """The last SAMPLE_PREFIX line wins; app log lines around it are ignored."""
    for line in reversed(stdout.splitlines()):
        if line.startswith(SAMPLE_PREFIX + " "):
            raw = json.loads(line[len(SAMPLE_PREFIX) + 1 :])
            return Sample(
                import_cpu_sec=float(raw["import_cpu_sec"]),
                modules=int(raw["modules"]),
                peak_rss_mb=float(raw["peak_rss_mb"]),
                gateway_cpu_sec=_optional_float(raw["gateway_cpu_sec"]),
            )
    raise ProbeError("probe printed no sample line")


def take_sample(python: Path, stubs: Sequence[str] = ()) -> Sample:
    cmd = [str(python), str(PROBE)]
    for name in stubs:
        cmd += ["--stub", name]
    with tempfile.TemporaryDirectory(prefix="myrm-startup-budget-") as data_dir:
        env = {**os.environ, "MYRM_DATA_DIR": data_dir, "PYTHONPATH": str(SERVER_DIR)}
        try:
            done = subprocess.run(
                cmd,
                cwd=SERVER_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=SAMPLE_TIMEOUT_SEC,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProbeError(f"probe exceeded {SAMPLE_TIMEOUT_SEC}s") from exc
    if done.returncode != 0:
        tail = done.stderr.strip().splitlines()[-1:] or ["no stderr"]
        raise ProbeError(f"probe exited {done.returncode}: {tail[0]}")
    return parse_sample(done.stdout)


def take_samples(count: int, stubs: Sequence[str] = ()) -> list[Sample]:
    python = server_python()
    if not python.exists():
        raise ProbeError(f"backend interpreter not found: {python}")
    return [take_sample(python, stubs) for _ in range(count)]
