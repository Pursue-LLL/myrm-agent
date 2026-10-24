"""Python toolchain probe for bash tool description injection.

Detects Python environment state (version, pip availability, PEP-668 status,
uv presence) at process startup and produces a single deterministic line.
This line is appended to the bash tool description so the LLM avoids blind
trial-and-error when installing packages.

Design principles:
- Zero token cost when environment is healthy (returns empty string).
- Cached per ``(PATH, VIRTUAL_ENV)``: the line describes an interpreter lookup, so a cache entry
  built under a different search path would describe a different environment.
- Never crashes — failures silently return empty string.
- A probe that times out is reported as unknown, never as absent: claiming "no pip module" for an
  interpreter whose probe merely outran its budget is a false statement the model acts on.
- Does NOT skip container environments (unlike Hermes): our agent runs
  inside the sandbox, so the probe is always relevant.

[INPUT]
- (none — reads host environment via subprocess)

[OUTPUT]
- get_environment_probe_line: Cached one-liner or "" if environment is clean.

[POS]
Python toolchain probe. Injects environment awareness into bash tool
description to eliminate pip install retry loops.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_CACHE_LOCK = threading.Lock()
_CACHE: dict[tuple[str, str], str] = {}
# One entry per distinct search path; a long-lived process sees a handful at most.
_MAX_CACHE_ENTRIES = 8


# Per-probe ceiling. Every probe is a `python -c` that returns in well under 100 ms on an idle
# machine; 0.8 s leaves room for a loaded host while keeping the worst case bounded.
_PROBE_TIMEOUT_S = 0.8

# Counts probes that could not reach a verdict; a build that saw one stays silent instead of
# reporting a false absence. It must be process-wide: the probes run on pool threads, so a
# thread-local counter would be written on the worker and read (as zero) on the caller.
_probe_failures_count = 0


def _note_probe_failure() -> None:
    global _probe_failures_count
    with _CACHE_LOCK:
        _probe_failures_count += 1


def _probe_failures() -> int:
    with _CACHE_LOCK:
        return _probe_failures_count

def _reset_probe_failures() -> None:
    global _probe_failures_count
    with _CACHE_LOCK:
        _probe_failures_count = 0


def _run(cmd: list[str], timeout: float = _PROBE_TIMEOUT_S) -> tuple[int, str, str]:
    """Run a short subprocess. Returns (returncode, stdout, stderr).

    Failures (binary missing, timeout, OSError) return (-1, "", "<reason>"); a timeout or an
    OSError also marks the build as inconclusive via :func:`_note_probe_failure`.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()
    except FileNotFoundError:
        return -1, "", "not found"
    except subprocess.TimeoutExpired:
        _note_probe_failure()
        return -1, "", "timeout"
    except OSError as exc:
        _note_probe_failure()
        return -1, "", f"oserror: {exc}"


def _python_version_of(binary: str) -> str | None:
    """Return version string like '3.12.4' for the given binary, or None."""
    if not shutil.which(binary):
        return None
    rc, out, _err = _run(
        [
            binary,
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
        ]
    )
    if rc == 0 and out:
        return out
    return None


def _has_pip_module(binary: str) -> bool:
    """True if `<binary> -m pip --version` succeeds."""
    if not shutil.which(binary):
        return False
    rc, _out, _err = _run([binary, "-m", "pip", "--version"])
    return rc == 0


def _detect_pep668(binary: str) -> bool:
    """True when the binary's install location is PEP-668 externally-managed."""
    if not shutil.which(binary):
        return False
    code = (
        "import sys, os;"
        "stdlib = os.path.dirname(os.__file__);"
        "marker = os.path.join(stdlib, 'EXTERNALLY-MANAGED');"
        "print('yes' if os.path.exists(marker) else 'no')"
    )
    rc, out, _err = _run([binary, "-c", code])
    return rc == 0 and out.strip() == "yes"


def _pip_python_version() -> str | None:
    """If `pip` is on PATH, return the Python version it's bound to.

    Parses the trailing `(python X.Y)` from `pip --version` output.
    """
    if not shutil.which("pip"):
        return None
    rc, out, _err = _run(["pip", "--version"])
    if rc != 0 or not out:
        return None
    if "(python " in out and out.endswith(")"):
        try:
            tail = out.rsplit("(python ", 1)[1]
            return tail[:-1].strip()
        except (IndexError, AttributeError):
            return None
    return None


def _build_probe_line() -> str:
    """Build the one-liner. Returns "" when nothing notable is detected.

    The interpreter probes are independent processes, so they run concurrently: serially they
    could each spend the full timeout and add up to seconds on the request path.
    """
    _reset_probe_failures()

    jobs: dict[str, Callable[[], object]] = {
        "py3_ver": lambda: _python_version_of("python3"),
        "py_ver": lambda: _python_version_of("python"),
        "pip_bound_to": _pip_python_version,
    }
    with ThreadPoolExecutor(max_workers=len(jobs), thread_name_prefix="env-probe") as pool:
        results = {name: pool.submit(job) for name, job in jobs.items()}
        py3_ver = results["py3_ver"].result()
        py_ver = results["py_ver"].result()
        pip_bound_to = results["pip_bound_to"].result()

    py3_has_pip = _has_pip_module("python3") if py3_ver else False
    py3_pep668 = _detect_pep668("python3") if py3_ver else False
    has_uv = shutil.which("uv") is not None

    if _probe_failures():
        # A timed-out probe is not evidence of absence. Stay silent rather than tell the model
        # that pip is missing or that a version mismatch exists.
        logger.debug("env_probe inconclusive: %d probe(s) failed", _probe_failures())
        return ""

    mismatch = bool(pip_bound_to and py3_ver and not py3_ver.startswith(pip_bound_to))

    silent_conditions = py3_ver is not None and py3_has_pip and not mismatch and (not py3_pep668 or has_uv)
    if silent_conditions:
        return ""

    bits: list[str] = []
    if py3_ver:
        py3_bit = f"python3={py3_ver}"
        if not py3_has_pip:
            py3_bit += " (no pip module)"
        bits.append(py3_bit)
    else:
        bits.append("python3=missing")

    if py_ver and py_ver != py3_ver:
        bits.append(f"python={py_ver}")
    elif not py_ver and py3_ver:
        bits.append("python=missing (use python3)")

    if pip_bound_to:
        if mismatch:
            bits.append(f"pip→python{pip_bound_to} (mismatch)")
        elif not py3_has_pip:
            bits.append(f"pip→python{pip_bound_to}")
    elif not py3_has_pip:
        bits.append("pip=missing")

    if py3_pep668:
        bits.append("PEP 668=yes (use venv or uv)")

    if has_uv:
        bits.append("uv=installed")

    if not bits:
        return ""

    return "Python toolchain: " + ", ".join(bits) + "."


def _cache_key() -> tuple[str, str]:
    """The environment this line describes.

    ``PATH`` decides which ``python3``/``pip``/``uv`` the probe finds and ``VIRTUAL_ENV`` shifts
    what those binaries report, so a line cached under one pair says nothing about another.
    """
    return (os.environ.get("PATH", ""), os.environ.get("VIRTUAL_ENV", ""))


def get_environment_probe_line(*, force_refresh: bool = False) -> str:
    """Return the probe line for the current environment, building it on first use.

    Returns "" when the environment is clean — the caller should skip appending anything then.

    Args:
        force_refresh: Rebuild the entry for the current environment before returning it.
    """
    key = _cache_key()
    with _CACHE_LOCK:
        if not force_refresh and key in _CACHE:
            return _CACHE[key]

    try:
        line = _build_probe_line()
    except Exception as exc:
        logger.debug("env_probe failed: %s", exc)
        line = ""

    with _CACHE_LOCK:
        if len(_CACHE) >= _MAX_CACHE_ENTRIES:
            _CACHE.clear()
        _CACHE[key] = line
    return line


def _reset_cache_for_tests() -> None:
    """Test helper — clear every cached environment."""
    with _CACHE_LOCK:
        _CACHE.clear()
