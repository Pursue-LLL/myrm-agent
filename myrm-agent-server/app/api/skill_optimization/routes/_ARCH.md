# api/skill_optimization/routes/

## 架构概述

技能版本与影子 A/B 子路由注册模块。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `ab_testing.py` | 模块 | 获取A/B测试列表 | ✅ |
| `versions.py` | 模块 | 获取skill的所有版本 | ✅ |
