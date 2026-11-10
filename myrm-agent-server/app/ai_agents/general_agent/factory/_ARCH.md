# general_agent/factory/

## 架构概述

GeneralAgent 装配包：按执行阶段拆成六个模块，`builder.py` 只保留编排顺序，包根 `__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `build_general_agent` 与内部测试使用的工具/Kanban/回调构造函数 | ✅ |
| `builder.py` | 编排 | 按阶段调用各模块并组装 `AgentRuntimeSpec`，最后调用 `create_skill_agent` | ✅ |
| `llms.py` | 阶段 | 主/轻量/回退 LLM 与隐私路由 | ✅ |
| `skills.py` | 阶段 | 存储后端、技能后端与运行时技能列表 | ✅ |
| `runtime.py` | 阶段 | 沙箱执行器、记忆回调/扩展与渠道通知工具 | ✅ |
| `middlewares.py` | 阶段 | 护栏、上下文管线、MoA 与 Human-tail 中间件顺序 | ✅ |
| `prompt.py` | 阶段 | 核心提示词与桌面/渠道/会话根目录补充 | ✅ |
| `support.py` | 支撑 | MCP OAuth 注入、Kanban 工具、技能评审与清理回调 | ✅ |

## 依赖关系

- `builder.py` → `llms.py`
- `builder.py` → `middlewares.py`
- `builder.py` → `prompt.py`
- `builder.py` → `runtime.py`
- `builder.py` → `skills.py`
- `builder.py` → `support.py`
- `middlewares.py` → `runtime.py`
- `middlewares.py` → `support.py`
