"""系统状态透传模块

Re-export from app.config.system_status（单一来源）。

[POS]
系统状态管理。记录如数据库降级、恢复等全局状态。
"""

from app.config.system_status import SystemStatus, system_status

__all__ = ["SystemStatus", "system_status"]
