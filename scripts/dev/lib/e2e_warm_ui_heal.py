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
_ATTACH_FLOCK_WAIT_SEC = 120.0
_ATTACH_SUBPROCESS_TIMEOUT_SEC = 180.0
_ATTACH_LEADER_STALE_SEC = 120.0
_ATTACH_FRONTEND_ENSURE_WAIT_SEC = 120.0


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


def _attach_heal_leader_meta_path() -> Path:
    return _state_dir() / "attach-frontend-heal.leader.json"


def _write_attach_leader_meta(owner_pid: int) -> None:
    import json

    payload = {"pid": owner_pid, "started_at": time.time()}
    _attach_heal_leader_meta_path().write_text(
        json.dumps(payload, separators=(",", ":")),
        encoding="utf-8",
    )


def _clear_attach_leader_meta() -> None:
    meta = _attach_heal_leader_meta_path()
    if meta.is_file():
        meta.unlink()


def _read_attach_leader_meta() -> tuple[int | None, float | None]:
    import json

    meta = _attach_heal_leader_meta_path()
    if not meta.is_file():
        return None, None
    try:
        payload = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None, None
    pid_raw = payload.get("pid")
    started_raw = payload.get("started_at")
    pid = int(pid_raw) if isinstance(pid_raw, int) or str(pid_raw).isdigit() else None
    started = float(started_raw) if started_raw is not None else None
    return pid, started


def _leader_process_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def attach_heal_leader_stale(*, stale_sec: float = _ATTACH_LEADER_STALE_SEC) -> bool:
    """True when meta points to a dead pid or a leader running longer than stale_sec."""
    pid, started = _read_attach_leader_meta()
    if pid is None:
        return False
    if not _leader_process_alive(pid):
        return True
    if started is None:
        return False
    return (time.time() - started) > stale_sec


def _ui_heal_global_flock_path() -> Path:
    return _state_dir() / "ui-heal-global.flock"


def warm_ui_heal_recently_applied(
    *, debounce_sec: float = _DEFAULT_DEBOUNCE_SEC
) -> bool:
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
                    "MYRM_FRONTEND_ENSURE_INNER": "1",
                    "MYRM_STACK_FRONTEND_WAIT_SEC": os.environ.get(
                        "MYRM_STACK_FRONTEND_WAIT_SEC", "360"
                    ),
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
        with urllib.request.urlopen(
            request, timeout=timeout_sec
        ) as response:  # noqa: S310
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
    wait_started = time.monotonic()
    deadline = wait_started + flock_wait_sec
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                _write_attach_leader_meta(os.getpid())
                break
            except BlockingIOError:
                if _shared_ui_probe_ok():
                    return "follower_ok"
                leader_pid, _leader_started = _read_attach_leader_meta()
                leader_alive = _leader_process_alive(leader_pid)
                elapsed = time.monotonic() - wait_started
                if attach_heal_leader_stale():
                    print(
                        "CHROME_E2E_HEAL_LEADER_STALE: attach frontend heal leader "
                        f"pid={leader_pid or 'unknown'} elapsed={elapsed:.0f}s — retry flock",
                        file=sys.stderr,
                    )
                if time.monotonic() >= deadline:
                    print(
                        "CHROME_E2E_HEAL_DEFER_TIMEOUT: attach frontend heal flock busy "
                        f"elapsed={elapsed:.0f}s leader_pid={leader_pid or 'unknown'} "
                        f"leader_alive={'yes' if leader_alive else 'no'}",
                        file=sys.stderr,
                    )
                    return "follower_timeout"
                print(
                    "CHROME_E2E_HEAL_DEFER: attach frontend heal flock busy — wait for leader "
                    f"elapsed={elapsed:.0f}s leader_pid={leader_pid or 'unknown'} "
                    f"leader_alive={'yes' if leader_alive else 'no'}",
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
                    "MYRM_FRONTEND_ENSURE_INNER": "1",
                    "MYRM_STACK_FRONTEND_WAIT_SEC": os.environ.get(
                        "MYRM_STACK_FRONTEND_WAIT_SEC",
                        str(int(_ATTACH_FRONTEND_ENSURE_WAIT_SEC)),
                    ),
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
            _clear_attach_leader_meta()
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _route_probe_ok(route: str, *, timeout_sec: float = 12.0) -> bool:
    import urllib.error
    import urllib.request

    ui_base = os.environ.get("MYRM_E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
    path = route if route.startswith("/") else f"/{route}"
    request = urllib.request.Request(f"{ui_base}{path}", method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(
            request, timeout=timeout_sec
        ) as response:  # noqa: S310
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def run_ui_heal_cli(
    monorepo_root: Path,
    *,
    route: str = "",
    flock_wait_sec: float = 120.0,
    slow_sec: float = 5.0,
) -> int:
    """Global single-flight ./myrm ui-heal — wave-safe, parallel pytest may continue."""
    if _shared_ui_probe_ok(timeout_sec=slow_sec):
        before = "ok"
    else:
        before = "fail"

    flock_file = _ui_heal_global_flock_path()
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
                if _shared_ui_probe_ok(timeout_sec=slow_sec):
                    print(f"MYRM_UI_HEAL: probe before={before}s")
                    print("MYRM_UI_HEAL_DEFER: global flock busy — UI already healthy")
                    if route and _route_probe_ok(route, timeout_sec=slow_sec):
                        ui_base = os.environ.get(
                            "MYRM_E2E_UI_BASE", "http://127.0.0.1:3000"
                        ).rstrip("/")
                        path = route if route.startswith("/") else f"/{route}"
                        print(f"MYRM_UI_HEAL: route OK {ui_base}{path}")
                    print(f"MYRM_UI_HEAL_OK ui=follower before={before} after=ok")
                    return 0
                if time.monotonic() >= deadline:
                    print(
                        "MYRM_UI_HEAL_FAIL: global ui-heal flock busy after "
                        f"{flock_wait_sec}s",
                        file=sys.stderr,
                    )
                    return 1
                time.sleep(2.0)

        print(f"MYRM_UI_HEAL: probe before={before}s")
        if not _shared_ui_probe_ok(timeout_sec=slow_sec):
            outcome = heal_shared_frontend_attach(monorepo_root)
            if outcome not in {"leader_ok", "follower_ok"}:
                print(
                    f"MYRM_UI_HEAL_FAIL: shared UI still unhealthy ({outcome})",
                    file=sys.stderr,
                )
                return 1

        post_deadline = time.monotonic() + float(
            os.environ.get("MYRM_UI_HEAL_POST_ENSURE_MAX_SEC", "120")
        )
        while time.monotonic() < post_deadline:
            if _shared_ui_probe_ok(timeout_sec=slow_sec):
                break
            time.sleep(2.0)
        else:
            print("MYRM_UI_HEAL_FAIL: root probe failed after heal", file=sys.stderr)
            return 1

        after = "ok"
        print(f"MYRM_UI_HEAL: probe after={after}s")

        if route:
            route_timeout = float(os.environ.get("MYRM_UI_HEAL_ROUTE_PROBE_SEC", "15"))
            if not _route_probe_ok(route, timeout_sec=route_timeout):
                ui_base = os.environ.get(
                    "MYRM_E2E_UI_BASE", "http://127.0.0.1:3000"
                ).rstrip("/")
                path = route if route.startswith("/") else f"/{route}"
                print(
                    f"MYRM_UI_HEAL_FAIL: route unreachable {ui_base}{path}",
                    file=sys.stderr,
                )
                return 1
            ui_base = os.environ.get(
                "MYRM_E2E_UI_BASE", "http://127.0.0.1:3000"
            ).rstrip("/")
            path = route if route.startswith("/") else f"/{route}"
            print(f"MYRM_UI_HEAL: route OK {ui_base}{path}")

        ui_base = os.environ.get("MYRM_E2E_UI_BASE", "http://127.0.0.1:3000").rstrip(
            "/"
        )
        print(f"MYRM_UI_HEAL_OK ui={ui_base} before={before} after={after}")
        return 0
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
    if len(sys.argv) >= 2 and sys.argv[1] == "ui-heal":
        root = Path(sys.argv[2]).resolve() if len(sys.argv) >= 3 else Path.cwd()
        route = ""
        idx = 3
        while idx < len(sys.argv):
            if sys.argv[idx] == "--route" and idx + 1 < len(sys.argv):
                route = sys.argv[idx + 1]
                idx += 2
                continue
            idx += 1
        return run_ui_heal_cli(root, route=route)
    if len(sys.argv) != 2:
        print("usage: e2e_warm_ui_heal.py <monorepo_root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    ok = heal_shared_frontend_debounced(root)
    print("healed" if ok else "skipped")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
