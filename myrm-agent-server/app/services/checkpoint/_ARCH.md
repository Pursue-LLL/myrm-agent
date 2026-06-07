# services/checkpoint/

## 架构概述

工作区快照拦截器：在破坏性操作前创建 Git 优先、文件复制降级的快照。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 | I/O/P |
|------|------|-------|
| `snapshot_service.py` | `SnapshotInterceptor` 实现 | ✅ |
