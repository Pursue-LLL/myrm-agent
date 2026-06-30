# canvas/ 服务架构

## 架构概述

Agent-facing canvas operations, SSE event hub, and LangChain agent tools.
Provides read/write access to tldraw canvas state for the GeneralAgent
and the REST API layer.

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 模块导出 | ✅ |
| `_paths.py` | 核心 | 共享文件系统路径工具：UUID 校验、路径构建、常量 | ✅ |
| `_events.py` | 核心 | SSE 事件通知中枢，供 API 和 services 层触发画布变更 | ✅ |
| `operations.py` | 核心 | Canvas state read、selection read、element insertion | ✅ |
| `canvas_agent_tools.py` | 核心 | 3 个 LangChain StructuredTool：get_state / get_selection / insert_element | ✅ |

## 依赖

- `_events.py`: 无外部依赖（leaf utility）
- `operations.py`: 依赖 `_paths.py`
- `canvas_agent_tools.py`: 依赖 `operations.py` + `_events.py`
- API 层 `api/canvas/router.py` 从 `_events.py` 导入 SSE 事件（正确方向：api → services）

## Agent 工具注册链路

```
frontend agent_config.enabled_builtin_tools["canvas"]
  → profile_resolver.resolve_builtin_tool_flags → enable_canvas=True
  → agent_config.canvas_id → GeneralAgentParams.canvas_id
  → tool_setup._setup_canvas_tools(deferred_tools)
  → factory.py: _flag_to_group includes "canvas"
  → _tool_layer_bootstrap.py: EXTENDED layer
```
