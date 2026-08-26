# services/checkpoint/

## 架构概述

工作区快照拦截器：在破坏性操作前通过 harness 层 FileSnapshotProtocol 工厂创建快照。负责 per-turn 去重（有界 LRU 缓存）、SSE 事件发射（纯数据 payload，UI 本地化文案）、多智能体元数据绑定。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 | I/O/P |
|------|------|-------|
| `snapshot_service.py` | `SnapshotInterceptor` — 业务编排层，委托 harness 工厂进行实际存储；`get_snapshot_interceptor()` 提供进程级单例，保证 per-turn 去重缓存跨 agent 创建存活；去重缓存上限 `_MAX_CACHED_TURNS=512` 防长进程内存增长 | ✅ |
| `persistence_service.py` | `SandboxPersistenceService` — 事件驱动增量持久化编排，集成 Harness 3 级 Fail-Closed 隐私阶梯与 Blake2b 原子密封校验（`IntegritySealer`）自愈隔离（Quarantine） | ✅ |
