"""Wave-scoped debounced shared frontend heal for warm_ui_route (R122 warm SSOT)."""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path

_DEFAULT_DEBOUNCE_SEC = 60.0
_DEFAULT_FLOCK_WAIT_SEC = 5.0
_ATTACH_FLOCK_WAIT_SEC = 300.0
_ATTACH_SUBPROCESS_TIMEOUT_SEC = 300.0


def _state_dir() -> Path:
    raw = os.environ.get(
        "MYRM_E2E_STATE_DIR",
        str(Path.home() / ".local" / "state" / "myrm-e2e"),
    )
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stamp_path() -> Path:
    return _state_dir() / "warm-ui-heal.stamp"


def _flock_path() -> Path:
    return _state_dir() / "warm-ui-heal.flock"


def _attach_heal_flock_path() -> Path:
    return _state_dir() / "attach-frontend-heal.flock"


def warm_ui_heal_recently_applied(*, debounce_sec: float = _DEFAULT_DEBOUNCE_SEC) -> bool:
    stamp = _stamp_path()
    if not stamp.is_file():
        return False
    try:
        last = float(stamp.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    return (time.time() - last) < debounce_sec


def _write_heal_stamp() -> None:
    _stamp_path().write_text(f"{time.time():.3f}\n", encoding="utf-8")


def heal_shared_frontend_debounced(
    monorepo_root: Path,
    *,
    debounce_sec: float = _DEFAULT_DEBOUNCE_SEC,
    flock_wait_sec: float = _DEFAULT_FLOCK_WAIT_SEC,
    subprocess_timeout_sec: float = 60.0,
) -> bool:
    """Run frontend-only ensure at most once per debounce window across parallel pytest."""
    if warm_ui_heal_recently_applied(debounce_sec=debounce_sec):
        return False

    dev_stack = monorepo_root / "myrm-agent" / "scripts" / "dev" / "dev-stack.sh"
    if not dev_stack.is_file():
        return False

    flock_file = _flock_path()
    flock_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(flock_file), os.O_RDWR | os.O_CREAT, 0o644)
    acquired = False
    deadline = time.monotonic() + flock_wait_sec
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.25)
        if warm_ui_heal_recently_applied(debounce_sec=debounce_sec):
            return False
        try:
            subprocess.run(
                ["bash", str(dev_stack), "frontend-only", "ensure"],
                cwd=str(monorepo_root),
                env={
                    **os.environ,
                    "MYRM_SUPERVISOR_BYPASS": "1",
                    "MYRM_E2E_SHPOIB": os.environ.get("MYRM_E2E_SHPOIB", "1"),
                    "MYRM_CHROME_E2E_FRONTEND_HEAL": "1",
                },
                capture_output=True,
                text=True,
                timeout=subprocess_timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False
        _write_heal_stamp()
        return True
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _shared_ui_probe_ok(*, timeout_sec: float = 12.0) -> bool:
    import urllib.error
    import urllib.request

    ui_base = os.environ.get("MYRM_E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
    request = urllib.request.Request(f"{ui_base}/", method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def heal_shared_frontend_attach(
    monorepo_root: Path,
    *,
    flock_wait_sec: float = _ATTACH_FLOCK_WAIT_SEC,
    subprocess_timeout_sec: float = _ATTACH_SUBPROCESS_TIMEOUT_SEC,
    poll_sec: float = 5.0,
) -> str:
    """Single-writer attach frontend heal across parallel chrome_e2e ADMIT sessions."""
    dev_stack = monorepo_root / "myrm-agent" / "scripts" / "dev" / "dev-stack.sh"
    if not dev_stack.is_file():
        return "missing_stack"

    flock_file = _attach_heal_flock_path()
    flock_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(flock_file), os.O_RDWR | os.O_CREAT, 0o644)
    acquired = False
    deadline = time.monotonic() + flock_wait_sec
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if _shared_ui_probe_ok():
                    return "follower_ok"
                if time.monotonic() >= deadline:
                    print(
                        "CHROME_E2E_HEAL_DEFER_TIMEOUT: attach frontend heal flock busy",
                        file=sys.stderr,
                    )
                    return "follower_timeout"
                print(
                    "CHROME_E2E_HEAL_DEFER: attach frontend heal flock busy — wait for leader",
                    file=sys.stderr,
                )
                time.sleep(poll_sec)
        try:
            proc = subprocess.run(
                ["bash", str(dev_stack), "frontend-only", "ensure"],
                cwd=str(monorepo_root),
                env={
                    **os.environ,
                    "MYRM_SUPERVISOR_BYPASS": "1",
                    "MYRM_E2E_SHPOIB": os.environ.get("MYRM_E2E_SHPOIB", "1"),
                    "MYRM_CHROME_E2E_FRONTEND_HEAL": "1",
                    "MYRM_E2E_ATTACH_FRONTEND_HEAL": "1",
                },
                capture_output=True,
                text=True,
                timeout=subprocess_timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "leader_timeout"
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[-400:]
            print(
                f"CHROME_E2E_HEAL: attach frontend ensure failed rc={proc.returncode} {detail}",
                file=sys.stderr,
            )
            return "leader_failed"
        _write_heal_stamp()
        return "leader_ok"
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "attach":
        if len(sys.argv) != 3:
            print("usage: e2e_warm_ui_heal.py attach <monorepo_root>", file=sys.stderr)
            return 2
        root = Path(sys.argv[2]).resolve()
        outcome = heal_shared_frontend_attach(root)
        print(outcome)
        return 0 if outcome in {"leader_ok", "follower_ok"} else 1
    if len(sys.argv) != 2:
        print("usage: e2e_warm_ui_heal.py <monorepo_root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    ok = heal_shared_frontend_debounced(root)
    print("healed" if ok else "skipped")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
