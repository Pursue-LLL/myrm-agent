# services/memory/life_milestones 模块架构

## 架构概述

人生里程碑与个人时间线：维护 Harness `LifeMilestonesSuite` 单例，首次创建时预置种子里程碑、成长日记与价值观演化节点（`_create_prepopulated_suite`），涉及隐私亲密等级 `PrivacyIntimacyLevel`；仅单用户本地数据。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 辅助 | 导出 provider 公共入口 | ✅ |
| `provider.py` | 核心 | `get_life_milestones_suite` / `reset_life_milestones_suite` 单例；`_create_prepopulated_suite` 预置数据 | ✅ |
