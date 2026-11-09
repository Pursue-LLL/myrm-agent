"""[INPUT]
- os.getppid (POS: 当前父进程)

[OUTPUT]
- start_parent_exit_watchdog: 父进程消失时向自身发送 SIGTERM

[POS]
探针/CI 实例的生命周期兜底。启动它的 shell 或 agent 可能不清理子进程，导致服务在后台继续
消耗资源；仅由 ``run.py --exit-with-parent`` 显式启用，避免守护进程/launchd 被误判。
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

_WATCH_INTERVAL_SEC = 1.0


def start_parent_exit_watchdog(
    *,
    interval_sec: float = _WATCH_INTERVAL_SEC,
    getppid: Callable[[], int] = os.getppid,
    send_signal: Callable[[int, int], None] = os.kill,
) -> threading.Thread | None:
    """SIGTERM this process once its parent changes; returns the daemon thread, or None when unused."""
    original_ppid = getppid()
    if original_ppid <= 1:
        # The launcher died before the watchdog started; the explicit flag means "do not outlive it".
        logger.warning("Parent process already gone; shutting down the probe instance")
        send_signal(os.getpid(), signal.SIGTERM)
        return None

    def watch() -> None:
        while True:
            time.sleep(interval_sec)
            if getppid() != original_ppid:
                logger.warning("Parent process %d exited; shutting down the probe instance", original_ppid)
                send_signal(os.getpid(), signal.SIGTERM)
                return

    thread = threading.Thread(target=watch, name="parent-exit-watchdog", daemon=True)
    thread.start()
    return thread
