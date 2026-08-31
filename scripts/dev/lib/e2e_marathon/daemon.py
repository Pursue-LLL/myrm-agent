"""Marathon supervisor daemon — serial chrome_e2e with checkpoint ledger."""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import TextIO

from e2e_marathon.ledger import MarathonLedger
from e2e_marathon.lock import acquire_lock, release_lock
from e2e_marathon.manifest import build_marathon_queue
from e2e_marathon.outcome import classify_outcome
from e2e_marathon.paths import MarathonPaths, resolve_paths
from e2e_marathon.runner import run_node
from e2e_marathon.rpc_types import MarathonCommand, MarathonRpcResponse

logger = logging.getLogger("e2e_marathon")


class MarathonDaemon:
    def __init__(self, paths: MarathonPaths) -> None:
        self.paths = paths
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._worker_token = f"marathon-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._ledger: MarathonLedger | None = None
        self._running = False

    def _ensure_ledger(self) -> MarathonLedger:
        loaded = MarathonLedger.load(self.paths.ledger_file)
        if loaded is not None and loaded.queue:
            self._ledger = loaded
            return loaded
        queue = build_marathon_queue(self.paths.monorepo_root)
        ledger = MarathonLedger.create(queue)
        ledger.save(self.paths.ledger_file)
        self._ledger = ledger
        return ledger

    def _heal_plane(self) -> None:
        heal_sh = self.paths.monorepo_root / "scripts" / "dev" / "e2e-context.sh"
        if heal_sh.is_file():
            subprocess.run(
                ["bash", str(heal_sh), "launch-check"],
                cwd=str(self.paths.monorepo_root),
                check=False,
            )

    def _run_queue(self) -> None:
        ledger = self._ensure_ledger()
        self._running = True
        try:
            for node_id in ledger.queue:
                if self._stop_event.is_set():
                    record = ledger.nodes.get(node_id)
                    if record is not None and record.outcome == "PENDING":
                        ledger.set_outcome(node_id, "INTERRUPTED", None, record.log_path)
                    continue
                record = ledger.nodes.get(node_id)
                if record is None:
                    continue
                if record.outcome in ("PASS", "SKIP"):
                    continue
                if record.index == 1 or record.index % 10 == 0:
                    self._heal_plane()
                logger.info("MARATHON_SPAWN i=R%d node=%s", record.index, node_id)
                try:
                    rc, log_path = run_node(self.paths, node_id, record.index)
                    log_text = log_path.read_text(encoding="utf-8", errors="replace")
                    outcome = classify_outcome(rc, log_text)
                except Exception as exc:
                    logger.exception("MARATHON_RUN_FAIL node=%s", node_id)
                    ledger.set_outcome(node_id, "INTERRUPTED", 1, None)
                    ledger.save(self.paths.ledger_file)
                    continue
                ledger.set_outcome(node_id, outcome, rc, str(log_path))
                ledger.save(self.paths.ledger_file)
                logger.info(
                    "MARATHON_%s i=R%d rc=%s node=%s",
                    outcome,
                    record.index,
                    rc,
                    node_id,
                )
        finally:
            self._running = False
            release_lock(self.paths.lock_file, os.getpid())
            ledger.save(self.paths.ledger_file)

    def start_worker(self) -> MarathonRpcResponse:
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return MarathonRpcResponse(
                ok=True,
                exit_code=0,
                stdout="MARATHON_OK: worker already running",
                stderr="",
                state=self.status_state(),
            )
        if not acquire_lock(self.paths.lock_file, os.getpid(), self._worker_token):
            return MarathonRpcResponse(
                ok=False,
                exit_code=2,
                stdout="",
                stderr="MARATHON_BUSY: another marathon holds the exclusive lock",
            )
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._run_queue,
            name="e2e-marathon-worker",
            daemon=True,
        )
        self._worker_thread.start()
        return MarathonRpcResponse(
            ok=True,
            exit_code=0,
            stdout="MARATHON_OK: worker started",
            stderr="",
            state=self.status_state(),
        )

    def status_state(self) -> dict[str, object]:
        ledger = MarathonLedger.load(self.paths.ledger_file)
        if ledger is None:
            return {"running": self._running, "ledger": None}
        summary = ledger.summary()
        summary["total"] = len(ledger.queue)
        summary["complete"] = ledger.is_complete()
        return {
            "running": self._running,
            "ledger": summary,
            "updated_at": ledger.updated_at,
        }

    def handle(self, command: MarathonCommand) -> MarathonRpcResponse:
        if command == "ping":
            return MarathonRpcResponse(ok=True, exit_code=0, stdout="pong", stderr="")
        if command == "status":
            return MarathonRpcResponse(
                ok=True,
                exit_code=0,
                stdout=json.dumps(self.status_state()),
                stderr="",
                state=self.status_state(),
            )
        if command == "start":
            return self.start_worker()
        if command == "shutdown":
            self._stop_event.set()
            return MarathonRpcResponse(
                ok=True,
                exit_code=0,
                stdout="MARATHON_OK: shutdown requested",
                stderr="",
            )
        return MarathonRpcResponse(
            ok=False,
            exit_code=1,
            stdout="",
            stderr=f"Invalid marathon cmd: {command}",
        )

    def serve(self) -> None:
        paths = self.paths
        paths.state_dir.mkdir(parents=True, exist_ok=True)
        if paths.sock_file.exists():
            paths.sock_file.unlink()
        server = socketserver.ThreadingUnixStreamServer(
            str(paths.sock_file),
            _MarathonRpcHandler,
        )
        server.daemon = self  # type: ignore[attr-defined]
        logger.info("Marathon supervisor listening on %s", paths.sock_file)
        try:
            server.serve_forever(poll_interval=0.5)
        finally:
            server.server_close()
            if paths.sock_file.exists():
                paths.sock_file.unlink(missing_ok=True)


class _MarathonRpcHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        daemon: MarathonDaemon = self.server.daemon  # type: ignore[attr-defined]
        line = self.rfile.readline()
        if not line.strip():
            return
        try:
            request = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            return
        command = request.get("cmd")
        if not isinstance(command, str):
            return
        response = daemon.handle(command)  # type: ignore[arg-type]
        payload = {
            "ok": response.ok,
            "exit_code": response.exit_code,
            "stdout": response.stdout,
            "stderr": response.stderr,
            "state": response.state,
        }
        self.wfile.write((json.dumps(payload) + "\n").encode("utf-8"))


def _write_pid_file(paths: MarathonPaths) -> None:
    paths.pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")


def _acquire_daemon_lock(paths: MarathonPaths) -> TextIO | None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = paths.state_dir / "marathon-supervisor.lock"
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def _daemonize() -> None:
    if os.fork() > 0:
        raise SystemExit(0)
    os.setsid()
    if os.fork() > 0:
        raise SystemExit(0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="e2e_marathon.daemon")
    parser.add_argument("--daemonize", action="store_true")
    args = parser.parse_args(argv)
    paths = resolve_paths()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(paths.daemon_log, encoding="utf-8")],
    )
    lock_handle = _acquire_daemon_lock(paths)
    if lock_handle is None:
        print("MARATHON_FAIL: another supervisor daemon holds the lock", file=sys.stderr)
        return 1
    if args.daemonize:
        _daemonize()
    _write_pid_file(paths)
    daemon = MarathonDaemon(paths)
    try:
        daemon.serve()
    finally:
        release_lock(paths.lock_file, os.getpid())
        if paths.pid_file.is_file():
            paths.pid_file.unlink(missing_ok=True)
        lock_handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
