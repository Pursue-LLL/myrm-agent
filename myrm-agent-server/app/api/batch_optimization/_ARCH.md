# api/batch_optimization 模块架构


## 架构概述

批量 Skill 优化 API。创建任务前强制 `create_batch_snapshot`；WebUI `batch-optimization` 页提供提交确认、运行中/排队中「取消并回滚」（`cleanup_strategy=rollback`）与详情页 terminal 回滚。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 路由导出 | — |
| `router.py` | 核心 | 批量优化 REST（创建前 `create_batch_snapshot`；`cancel` 支持 `cleanup_strategy=rollback`；terminal 回滚调 `restore_skill_snapshot`） | ✅ |
