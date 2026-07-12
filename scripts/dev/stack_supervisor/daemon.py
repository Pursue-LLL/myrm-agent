"""Dev stack supervisor daemon — single writer for ensure/reset, live watchdog.

[INPUT]
  stack_supervisor.paths::StackPaths (POS: dev 栈路径 SSOT)
  stack_supervisor.probe::probe_stack (POS: live 探活)
  stack_supervisor.state_gc::collect_stale_state (POS: 失效状态 GC)

[OUTPUT]
  SupervisorDaemon: Unix socket RPC 服务 + 看门狗 + 失温冷却自愈（intentional reset 清除自愈记忆）

[POS]
  本地 dev 栈单写者守护进程。串行化 ensure/reset，30s 探活 GC + 失温冷却自愈。
"""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from stack_supervisor.state_gc import collect_stale_state, write_supervisor_state
from stack_supervisor.paths import StackPaths, resolve_paths
from stack_supervisor.probe import StackProbe, probe_stack, stack_warm
from stack_supervisor.rpc_types import RpcCommand, RpcResponse

logger = logging.getLogger("stack_supervisor")
WATCHDOG_INTERVAL_SEC = float(os.environ.get("MYRM_SUPERVISOR_WATCHDOG_SEC", "30"))
HEAL_COOLDOWN_SEC = float(os.environ.get("MYRM_SUPERVISOR_HEAL_COOLDOWN_SEC", "300"))


@dataclass
class SupervisorDaemon:
    paths: StackPaths
    _op_lock: threading.Lock
    _stop_event: threading.Event
    _watchdog_thread: threading.Thread | None
    _last_stack_warm_at: float | None
    _last_auto_heal_at: float

    @classmethod
    def create(cls, paths: StackPaths | None = None) -> SupervisorDaemon:
        resolved = paths if paths is not None else resolve_paths()
        return cls(
            paths=resolved,
            _op_lock=threading.Lock(),
            _stop_event=threading.Event(),
            _watchdog_thread=None,
            _last_stack_warm_at=None,
            _last_auto_heal_at=0.0,
        )

    def _dev_stack_env(self, overrides: dict[str, str] | None = None) -> dict[str, str]:
        env = os.environ.copy()
        env["MYRM_SUPERVISOR_BYPASS"] = "1"
        env["AGENT_ROOT"] = str(self.paths.agent_root)
        env["SERVER_DIR"] = str(self.paths.server_dir)
        env["FRONTEND_DIR"] = str(self.paths.frontend_dir)
        env["MYRM_DEV_STATE_DIR"] = str(self.paths.state_dir)
        if overrides:
            env.update(overrides)
        return env

    def _run_dev_stack(
        self,
        command: str,
        timeout_sec: float,
        env_overrides: dict[str, str] | None = None,
    ) -> RpcResponse:
        if not self.paths.dev_stack_sh.is_file():
            return RpcResponse(
                ok=False,
                exit_code=1,
                stdout="",
                stderr=f"Missing dev-stack.sh at {self.paths.dev_stack_sh}",
            )
        try:
            result = subprocess.run(
                ["bash", str(self.paths.dev_stack_sh), command],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
                env=self._dev_stack_env(env_overrides),
            )
        except subprocess.TimeoutExpired as exc:
            return RpcResponse(
                ok=False,
                exit_code=1,
                stdout=exc.stdout or "",
                stderr=(exc.stderr or "") + f"\nTimeout running dev-stack {command}",
            )
        return RpcResponse(
            ok=result.returncode == 0,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def _watchdog_once(self) -> None:
        probe, gc_action = collect_stale_state(self.paths)
        write_supervisor_state(self.paths, probe, gc_action)
        if any(
            (
                gc_action.cleared_warmth,
                gc_action.cleared_epoch,
                gc_action.cleared_backend_pid,
                gc_action.cleared_frontend_pid,
            )
        ):
            logger.info("GC actions: %s", gc_action)
        self._maybe_auto_heal(probe)

    def _maybe_auto_heal(self, probe: StackProbe) -> None:
        now = time.monotonic()
        if stack_warm(probe):
            self._last_stack_warm_at = now
            return
        if self._last_stack_warm_at is None:
            return
        if now - self._last_auto_heal_at < HEAL_COOLDOWN_SEC:
            return
        if probe.api_http_ok and probe.frontend_http_ok:
            return
        if not self._op_lock.acquire(blocking=False):
            return
        try:
            if time.monotonic() - self._last_auto_heal_at < HEAL_COOLDOWN_SEC:
                return
            logger.info("Watchdog auto-heal: stack lost warmth — running ensure once")
            ensure_wait = float(os.environ.get("MYRM_STACK_FRONTEND_WAIT_SEC", "180"))
            result = self._run_dev_stack("ensure", timeout_sec=ensure_wait + 30.0)
            self._last_auto_heal_at = time.monotonic()
            if result.ok:
                logger.info("Watchdog auto-heal: ensure succeeded")
                refreshed = probe_stack(self.paths)
                if stack_warm(refreshed):
                    self._last_stack_warm_at = time.monotonic()
            else:
                logger.warning("Watchdog auto-heal: ensure failed (rc=%s)", result.exit_code)
        finally:
            self._op_lock.release()

    def _watchdog_loop(self) -> None:
        while not self._stop_event.wait(WATCHDOG_INTERVAL_SEC):
            try:
                self._watchdog_once()
            except Exception:
                logger.exception("Watchdog iteration failed")

    def start_watchdog(self) -> None:
        if self._watchdog_thread is not None:
            return
        self._watchdog_once()
        thread = threading.Thread(target=self._watchdog_loop, name="stack-watchdog", daemon=True)
        thread.start()
        self._watchdog_thread = thread

    def stop_watchdog(self) -> None:
        self._stop_event.set()
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=2.0)

    def handle(self, command: RpcCommand, env_overrides: dict[str, str] | None = None) -> RpcResponse:
        if command == "ping":
            probe = probe_stack(self.paths)
            return RpcResponse(
                ok=True,
                exit_code=0,
                stdout="SUPERVISOR_PONG\n",
                stderr="",
                state={"stack_warm": stack_warm(probe), "epoch": probe.epoch},
            )

        if command == "shutdown":
            self.stop_watchdog()
            return RpcResponse(ok=True, exit_code=0, stdout="SUPERVISOR_SHUTDOWN_OK\n", stderr="")

        if command == "status":
            probe, _ = collect_stale_state(self.paths)
            write_supervisor_state(self.paths, probe)
            dev = self._run_dev_stack("status", timeout_sec=15.0, env_overrides=env_overrides)
            return RpcResponse(
                ok=dev.ok,
                exit_code=dev.exit_code,
                stdout=dev.stdout,
                stderr=dev.stderr,
                state={
                    "stack_warm": stack_warm(probe),
                    "api_http_ok": probe.api_http_ok,
                    "frontend_http_ok": probe.frontend_http_ok,
                    "epoch": probe.epoch,
                },
            )

        if command == "attach":
            attach_wait = float(
                (env_overrides or {}).get(
                    "MYRM_STACK_ATTACH_WAIT_SEC",
                    os.environ.get("MYRM_STACK_ATTACH_WAIT_SEC", "120"),
                )
            )
            dev = self._run_dev_stack(
                "attach",
                timeout_sec=attach_wait + 5.0,
                env_overrides=env_overrides,
            )
            probe = probe_stack(self.paths)
            return RpcResponse(
                ok=dev.ok,
                exit_code=dev.exit_code,
                stdout=dev.stdout,
                stderr=dev.stderr,
                state={"stack_warm": stack_warm(probe)},
            )

        with self._op_lock:
            self._watchdog_once()
            if command == "reset":
                dev = self._run_dev_stack("reset", timeout_sec=120.0, env_overrides=env_overrides)
                self._watchdog_once()
                if dev.ok:
                    self._last_stack_warm_at = None
                return dev
            if command == "ensure":
                ensure_wait = float(
                    (env_overrides or {}).get(
                        "MYRM_STACK_FRONTEND_WAIT_SEC",
                        os.environ.get("MYRM_STACK_FRONTEND_WAIT_SEC", "180"),
                    )
                )
                dev = self._run_dev_stack(
                    "ensure",
                    timeout_sec=ensure_wait + 30.0,
                    env_overrides=env_overrides,
                )
                self._watchdog_once()
                if dev.ok:
                    self._last_stack_warm_at = time.monotonic()
                return dev

        return RpcResponse(ok=False, exit_code=1, stdout="", stderr=f"Unknown command: {command}")

    def serve_forever(self) -> None:
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        if self.paths.supervisor_sock.exists():
            self.paths.supervisor_sock.unlink()

        self.start_watchdog()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.paths.supervisor_sock))
        server.listen(8)
        logger.info("Supervisor listening on %s", self.paths.supervisor_sock)

        try:
            while not self._stop_event.is_set():
                try:
                    server.settimeout(1.0)
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                with conn:
                    self._handle_connection(conn)
        finally:
            server.close()
            if self.paths.supervisor_sock.exists():
                self.paths.supervisor_sock.unlink()

    def _handle_connection(self, conn: socket.socket) -> None:
        conn.settimeout(600.0)
        raw = b""
        while not raw.endswith(b"\n"):
            block = conn.recv(4096)
            if not block:
                break
            raw += block
        if not raw.strip():
            return
        request = json.loads(raw.decode("utf-8"))
        command = request.get("cmd")
        env_overrides = request.get("env")
        if not isinstance(env_overrides, dict):
            env_overrides = None
        else:
            env_overrides = {str(k): str(v) for k, v in env_overrides.items()}
        if command not in ("ensure", "attach", "reset", "status", "ping", "shutdown"):
            response = RpcResponse(ok=False, exit_code=1, stdout="", stderr=f"Invalid cmd: {command}")
        else:
            response = self.handle(command, env_overrides=env_overrides)  # type: ignore[arg-type]

        payload: dict[str, object] = {
            "ok": response.ok,
            "exit_code": response.exit_code,
            "stdout": response.stdout,
            "stderr": response.stderr,
        }
        if response.state is not None:
            payload["state"] = response.state
        conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))


def _write_pid_file(paths: StackPaths) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.supervisor_pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")


def _daemonize() -> None:
    if os.fork() > 0:
        raise SystemExit(0)
    os.setsid()
    if os.fork() > 0:
        raise SystemExit(0)
    os.chdir("/")
    sys.stdout.flush()
    sys.stderr.flush()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    paths = resolve_paths()
    daemonize_flag = "--daemonize" in sys.argv

    if daemonize_flag:
        _daemonize()

    _write_pid_file(paths)

    def _on_signal(_signum: int, _frame: object) -> None:
        daemon.stop_watchdog()
        if paths.supervisor_pid_file.is_file():
            paths.supervisor_pid_file.unlink()
        raise SystemExit(0)

    daemon = SupervisorDaemon.create(paths)
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    try:
        daemon.serve_forever()
    finally:
        if paths.supervisor_pid_file.is_file():
            paths.supervisor_pid_file.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
