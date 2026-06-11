# services/checkpoint/

## 架构概述

工作区快照拦截器：在破坏性操作前通过 harness 层 FileSnapshotProtocol 工厂创建快照。负责 per-turn 去重、SSE 事件发射、多智能体元数据绑定。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 | I/O/P |
|------|------|-------|
| `snapshot_service.py` | `SnapshotInterceptor` — 业务编排层，委托 harness 工厂进行实际存储 | ✅ |
