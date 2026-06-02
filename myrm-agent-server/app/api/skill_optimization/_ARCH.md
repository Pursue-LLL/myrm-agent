# api/skill_optimization 模块架构


## 架构概述

Skill 优化系统 API。提供仪表盘、质量监控、版本管理、A/B 测试、批量优化等接口，
包含 WebSocket 实时批量进度推送。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 路由导出 | — |
| `router.py` | 核心 | Skill 优化 REST 接口 | ⚠️ 待补 |
| `metrics_provider.py` | 核心 | 优化指标数据提供者 | ⚠️ 待补 |
| `ws_batch_progress.py` | 辅助 | WebSocket 批量优化进度推送 | ⚠️ 待补 |
