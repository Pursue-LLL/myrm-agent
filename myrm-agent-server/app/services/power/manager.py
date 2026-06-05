"""
[INPUT]
None (POS: 基础系统工具库)

[OUTPUT]
PowerManager: 提供智能电源锁防休眠，并感知电池电量。

[POS]
电源与系统状态管理。在长时间任务（如 OfflineDurableTask）期间防止系统休眠。
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)

_power_locks: Dict[str, object] = {}


def acquire_power_lock(task_id: str) -> bool:
    """Acquire system power lock to prevent sleep during long tasks."""
    try:
        import psutil
        from wakepy import keep

        battery = psutil.sensors_battery()
        if battery and not battery.power_plugged and battery.percent < 15:
            logger.warning(f"🔋 Battery low ({battery.percent}%), refusing to acquire power lock for task {task_id}")
            return False

        lock = keep.running()
        success = lock.__enter__()
        if success:
            _power_locks[task_id] = lock
            logger.info(f"🔋 Power lock acquired for task {task_id}")
            return True
        else:
            logger.warning(f"🔋 Failed to acquire power lock for task {task_id}")
            return False
    except Exception as e:
        logger.error(f"Error acquiring power lock: {e}")
        return False


def release_power_lock(task_id: str) -> None:
    """Release system power lock."""
    try:
        lock = _power_locks.pop(task_id, None)
        if lock:
            lock.__exit__(None, None, None)
            logger.info(f"🔋 Power lock released for task {task_id}")
    except Exception as e:
        logger.error(f"Error releasing power lock: {e}")
