"""WebSocket 连接恢复与心跳探测控制器的包入口。

[INPUT]
- app.api.ws.connection_controller (POS: 带抖动指数退避的连接状态机)
- app.api.ws.heartbeat (POS: 自适应间隔的心跳探针与死线截断)

[OUTPUT]
- ConnectionController, ConnectionState, BackoffConfig, JitteredBackoffScheduler: 连接恢复控制
- AdaptiveHeartbeatController, HeartbeatConfig, HeartbeatStats: 心跳探测控制

[POS]
把连接恢复与心跳探测两组控制器作为同一个包导出，调用方只依赖包名，不依赖内部模块划分。
"""

from __future__ import annotations

from app.api.ws.connection_controller import (
    BackoffConfig,
    ConnectionController,
    ConnectionState,
    JitteredBackoffScheduler,
)
from app.api.ws.heartbeat import (
    AdaptiveHeartbeatController,
    HeartbeatConfig,
    HeartbeatStats,
)

__all__ = [
    "AdaptiveHeartbeatController",
    "BackoffConfig",
    "ConnectionController",
    "ConnectionState",
    "HeartbeatConfig",
    "HeartbeatStats",
    "JitteredBackoffScheduler",
]
