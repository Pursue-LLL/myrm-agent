# services/memory/context_hooks 模块架构

## 架构概述

可插拔上下文 Hook 管线与记忆注入：维护 Harness `ContextHookPipelineSuite` 进程级单例，预装三个内置拦截器：环境守卫（`_env_guard_hook`）、提示词增强（`_prompt_enrich_hook`）、出口脱敏（`_egress_redactor_hook`，匹配 `sk-` / `ghp_` 令牌与 `password=` 形态）。仅单用户沙箱，不含多租户语义。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 辅助 | 导出 provider 公共入口 | ✅ |
| `provider.py` | 核心 | `get_context_hook_suite` / `reset_context_hook_suite`：单例获取与重置；`_create_prepopulated_suite` 装配内置 Hook 并按 `ContextHookStage` 与 `HookExecutionPriority` 注册 | ✅ |
