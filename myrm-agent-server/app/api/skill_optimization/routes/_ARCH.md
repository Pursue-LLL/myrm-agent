# api/skill_optimization/routes/

## 架构概述

本目录模块说明。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `ab_testing.py` | 模块 | 获取A/B测试列表 | ✅ |
| `dashboard.py` | 模块 | active_optimizations: int | ✅ |
| `optimization.py` | 模块 | 手动触发优化请求 | ✅ |
| `system.py` | 模块 | 健康检查API，返回scheduler和storage的健康状态。 | ✅ |
| `versions.py` | 模块 | 获取skill的所有版本 | ✅ |
