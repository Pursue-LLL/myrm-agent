# app/core/utils/errors 子包架构

API 错误工具。异常基类、HTTP 错误工厂、FastAPI 异常处理器、脱敏与 LLM 异常归一，按职责分模块；`app.core.utils.errors` 导入路径不变（86 个调用点）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合全部公开符号（`MyrmError`、HTTP 工厂、`register_exception_handlers`、`handle_llm_exception` 等） | — |
| `constants.py` | 辅助 | logger、业务码 → HTTP 映射、failover reason 映射、home 路径正则 | ✅ |
| `base.py` | 核心 | `MyrmError`（业务码、状态码覆盖、payload）与共享的 `_classify_exception` | ✅ |
| `http.py` | 核心 | `StandardHTTPException` 与 validation / not_found / auth / permission / conflict / internal / timeout / rate-limit 等错误工厂 | ✅ |
| `handlers.py` | 核心 | `register_exception_handlers`：把未捕获异常、校验错误、MyrmError 映射成统一响应 | ✅ |
| `redaction.py` | 辅助 | home 路径折叠、错误 payload 脱敏、错误消息格式化与记录 | ✅ |
| `llm.py` | 核心 | `handle_llm_exception`：把 LLM/网络异常归一成业务错误码与用户提示 | ✅ |

## 依赖关系

- 上游：`fastapi` / `pydantic` / `starlette`、harness 的 LLM 错误分类
- 下游：`app/api/**`、`app/services/**`（86 个模块直接导入本包）
