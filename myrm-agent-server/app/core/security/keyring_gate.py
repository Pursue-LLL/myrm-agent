"""
[INPUT]
None

[OUTPUT]
KeyringGate: 在守护线程里执行 OS 钥匙串调用并限时，授权弹窗或钥匙串服务无响应时不会冻结调用方

[POS]
钥匙串访问的有界执行器。供 master_key 读写 OS Keyring：macOS 上 SecItemCopyMatching 会等待 securityd，
二进制身份变化后可能挂在授权弹窗上，同步调用会把事件循环（以及整个服务启动）卡死。
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class _Call[T]:
    done: threading.Event = field(default_factory=threading.Event)
    value: T | None = None


class KeyringGate:
    """Runs one OS keyring call at a time without letting it block the caller past ``timeout_sec``.

    A call that outlives the timeout keeps running on its own daemon thread, so it can neither block interpreter
    exit nor be killed. While it is outstanding, later calls return at once instead of queueing behind the same
    prompt, and its eventual result is handed to ``on_late``.
    """

    def __init__(self, timeout_sec: float) -> None:
        self._timeout_sec = timeout_sec
        self._lock = threading.Lock()
        self._stalled: threading.Event | None = None

    def run[T](self, call: Callable[[], T | None], on_late: Callable[[T], None]) -> T | None:
        """Return the result of ``call``, or None when it failed, returned None, or did not finish in time."""
        pending = _Call[T]()
        with self._lock:
            if self._stalled is not None:
                logger.debug("Keyring call skipped: a previous call is still waiting on the OS keyring.")
                return None
            threading.Thread(target=self._work, args=(call, pending, on_late), name="keyring-call", daemon=True).start()

        if not pending.done.wait(self._timeout_sec):
            with self._lock:
                # The worker may have finished between the wait timing out and taking the lock.
                if not pending.done.is_set():
                    self._stalled = pending.done
                    logger.warning(
                        "OS keyring did not answer within %.0fs (an authorization prompt may be open); continuing without it.",
                        self._timeout_sec,
                    )
                    return None
        return pending.value

    def _work[T](self, call: Callable[[], T | None], pending: _Call[T], on_late: Callable[[T], None]) -> None:
        try:
            value = call()
        except Exception as exc:
            logger.debug("Keyring call failed (non-fatal): %s", exc)
            value = None

        with self._lock:
            pending.value = value
            pending.done.set()
            was_stalled = self._stalled is pending.done
            if was_stalled:
                self._stalled = None

        if was_stalled and value is not None:
            on_late(value)
