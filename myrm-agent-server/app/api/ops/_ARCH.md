# ops 模块

---

## 架构概述

提供统一的单机与沙箱 Ops 运行态聚合快照能力，聚合 System、Liveness、Resources/RSS、Channels、Governance/Badges、UsageRadar、Memory、DoctorSummary。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `router.py` | 路由入口 | 暴露 `GET /api/v1/ops/snapshot`，支持 `include_doctor` 极速/深度双模态查询 | ✅ |

关联服务：`app/services/ops/snapshot_service.py`（无状态并发采集服务，带独立 Session 隔离与 2.0s 探针超时熔断）。
关联模型：`app/schemas/ops.py`（Pydantic V2 强类型 DTO 数据契约）。
测试：`tests/api/ops/test_ops_snapshot.py`。
