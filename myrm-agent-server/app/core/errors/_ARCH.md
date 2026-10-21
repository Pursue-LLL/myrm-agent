# core/errors 模块架构


## 架构概述

LLM 错误业务URL映射器。将Harness层的标准化错误代码映射为业务层的recovery_actions（包含可点击的操作按钮和业务URL），供Frontend渲染。Sandbox 部署（`uses_platform_budget`）下 `BILLING` 的 `top_up` 动作指向 `/subscription`；Local BYOK 仍指向 `/pricing`。

**职责边界**：
- ✅ 负责：错误代码 → recovery_actions映射（业务URL）
- ❌ 不负责：错误类型定义（由Harness层error_types.py负责）
- ❌ 不负责：错误翻译（由Harness层LLMErrorDiagnostic负责）

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 错误处理函数导出 | ✅ |
| `llm_errors.py` | 核心 | Recovery actions URL映射器。支持11种错误代码（RATE_LIMIT, OVERLOADED, TIMEOUT, BILLING, AUTH_PERMANENT, SESSION_EXPIRED, MODEL_NOT_FOUND, FORMAT_ERROR, RESPONSE_FORMAT_ERROR, CONTEXT_OVERFLOW, UNKNOWN）到业务URL的映射，生成可点击操作按钮供Frontend渲染 | ✅ |
