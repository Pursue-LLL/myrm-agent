# platform_utils/sandbox/entitlements/

## 架构概述

SaaS 沙箱 entitlement 解析：从 Control Plane internal API 拉取计划能力位与 Work Unit 预算，供功能门禁与配额 UI 消费。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `entitlement_guard.py` | 核心 | 沙箱 entitlement 守卫：解析 CP 返回的计划与功能开关；`require_cron_slot` 由 `core/cron/adapters/entitlement_guarded_manager.py` 在 job 创建/复制时调用 | — |
| `platform_budget_adapter.py` | 核心 | Control Plane Work Unit 预算适配器，对接 harness `BudgetStatus` | — |

## 依赖

- `app.config.settings` — Control Plane 基址与认证
- `myrm_agent_harness.utils.token_economics.budget_guard` — 预算状态类型
