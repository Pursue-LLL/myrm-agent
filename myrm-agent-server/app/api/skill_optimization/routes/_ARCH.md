# api/skill_optimization/routes/

## 架构概述

技能版本子路由注册模块。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `versions.py` | 模块 | 获取skill的所有版本；批次撤销 `POST /mutations/{batch_id}/rollback` 在被拒时回 409，`detail.code` 区分原因：`batch_already_consumed`（已撤销或未知批次）、`batch_superseded`（同一 skill 之后还有未撤销的较新批次，须先撤销它）、`skill_missing`（skill 已被删除）、`compensation_failed`（恢复失败且补偿也失败）、`rollback_failed`（其余恢复失败），前端按码给出本地化提示 | ✅ |
