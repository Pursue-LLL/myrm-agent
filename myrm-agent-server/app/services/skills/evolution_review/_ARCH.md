# skills/evolution_review/ 模块架构

## 架构概述

Evolution 审核子域。以 `ApprovalRecord` 为唯一事实源，提供类型（DTO/枚举/常量）、持久化、只读查询、写操作与落盘编排。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.py` | 核心 | 审核域类型：`EvolutionReviewRecord` / `EvolutionApprovalPayload` / `RuntimeFailureEvidence` / 状态枚举 / `EVOLUTION_ACTION_TYPE` / `MAX_SKILL_CONTENT_CHARS` 常量 / `ApprovalRecord` 转换 | ✅ |
| `persistence.py` | 核心 | ApprovalRecord 持久化读写（list/count 下推 SQL LIMIT + pending growth_status 过滤） | ✅ |
| `queries.py` | 核心 | 创建与只读查询（list/count 委托 persistence SQL） | ✅ |
| `actions.py` | 核心 | 审批 / 拒绝 / 修订 / 回滚 | ✅ |
| `disk.py` | 核心 | 落盘编排（description / shadow / approval 成功路径） | ✅ |
| `disk_content.py` | 核心 | 全量内容 apply + rollback（含 fork） | ✅ |

## 设计原则

- **事实源**：所有审核状态以 `ApprovalRecord` 行为事实源，`evolution_review` 只做投影与操作，不另设状态表。
- **依赖方向**：types ← persistence ← queries/disk_content ← disk ← actions 单向依赖；跨子域引用根模块 `experience_ledger`（账本）时使用 `..experience_ledger` 相对导入。
- **IMPORT CONSTRAINT**：本包不做聚合导出（条件性依赖环见 `__init__.py`），外部一律穿透导入子模块；公共 API 由门面 `../evolution_reviews.py` 统一 re-export。
