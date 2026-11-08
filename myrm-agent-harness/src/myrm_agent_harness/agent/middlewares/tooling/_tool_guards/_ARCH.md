# middlewares/tooling/_tool_guards/

## 架构概述

工具拦截的调用前/后守卫：`pre_call` 决定是否放行，`post_call` 改写结果；`shared` 提供共用事件与阶段间状态。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `PreCallResult` / `run_pre_call_guards` / `run_post_call_guards` | ✅ |
| `shared.py` | 核心 | 循环守卫 STATUS 事件、`PreCallResult` 状态载体 | ✅ |
| `pre_call.py` | 核心 | 急停、熔断、循环、回合预算、steering、信任与 PII 检查 | ✅ |
| `post_call.py` | 核心 | 预算截断、投毒检测、污点、hook 校验与循环记录 | ✅ |

## 依赖关系

- `post_call.py` → `shared.py`
- `pre_call.py` → `shared.py`
