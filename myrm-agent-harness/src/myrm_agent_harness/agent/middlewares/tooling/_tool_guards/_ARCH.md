# middlewares/tooling/_tool_guards/

## 架构概述

工具拦截的调用前/后守卫：`pre_call` 决定是否放行，`post_call` 改写结果；`shared` 提供共用事件与阶段间状态。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `PreCallResult` / `run_pre_call_guards` / `run_post_call_guards` | ✅ |
| `shared.py` | 核心 | 循环守卫 STATUS 事件、`PreCallResult` 状态载体 | ✅ |
| `pre_call.py` | 核心 | 急停、熔断、循环、回合预算、steering、信任与 PII 检查；调用不存在的工具时，只有本次运行绑定了 `skill_select_tool`，错误里才附带指向它的技能提示 | ✅ |
| `post_call.py` | 核心 | 结果进入对话的第一步，先让文本可被 UTF-8 编码：非 UTF-8 的文件名在 Python 里是孤立代理项，循环守卫的结果哈希与超预算结果的落盘都按严格 UTF-8 编码、会因它抛 `UnicodeEncodeError`，所以换成 `U+FFFD`（与发往模型时的替换一致；本来就可编码的结果保持同一个对象，状态与附加字段不变）；随后是预算截断、投毒检测、污点、hook 校验与循环记录 | ✅ |

## 依赖关系

- `post_call.py` → `shared.py`
- `post_call.py` → `toolkits/llms/adapters/chat_model/wire_encoding.py`（`encodable_text`）
- `pre_call.py` → `shared.py`
