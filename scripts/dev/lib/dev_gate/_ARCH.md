# dev_gate 模块架构

## 架构概述

Dev Gate 协调层：session 注册、lease/credit、launch-check、cleanup.sealed。P1 domain repack（2026-08-11）。

## 文件清单

| 文件 | 职责 |
|------|------|
| `contract.py` | 超时、token、pytest floor SSOT |
| `session.py` | ExecutionMode / AccessScope / 状态机 |
| `store.py` | SQLite WAL registry + event journal |
| `coordinator.py` | Unix socket 协调器 serve loop |
| `cli.py` | submit/finish/reap 客户端 |
| `status.py` | e2e-context registry 快照 |
| `async_queue.py` | 异步写入队列 |
| `event_hub.py` / `event_wait.py` | 事件分发与等待 |
| `signoff_export.py` | signoff artifact 导出 |
| `private_resource_controller.py` | PRIVATE 1–4 credits 队列 |
| `solo_launch_gate.py` | 维护者 signoff 窗口 |
| `cleanup_observed_seal.py` | observed cleanup seal |
| `desktop_seat_controller.py` | macOS GUI seat |
| `owner_identity.py` | pid + boot token 精确 owner |

## 兼容层

`dev/lib/dev_gate/*` 为 canonical 实现，所有调用方经 `from dev_gate.* import ...` 导入。

## 依赖

- [../_ARCH.md](../_ARCH.md)
