# api/features 模块架构


## 架构概述

Feature Flags API。提供功能开关状态查询和实验功能切换接口，供前端使用。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 路由导出 | — |
| `router.py` | 核心 | Feature Flags REST 接口（查询、切换、重置） | ⚠️ 待补 |
