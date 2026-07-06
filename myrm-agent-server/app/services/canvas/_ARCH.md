# canvas/ 服务架构

## 架构概述

Agent-facing canvas operations, SSE event hub, layout algorithms, and LangChain agent tools.
Provides read/write access to tldraw canvas state for the GeneralAgent
and the REST API layer.

All snapshot write operations are protected by a per-canvas `asyncio.Lock` pool
(`_canvas_locks`) to prevent lost updates when frontend auto-save and Agent
read-modify-write operations race on the same snapshot file.

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 模块导出 | ✅ |
| `_paths.py` | 核心 | 共享文件系统路径工具：UUID 校验、路径构建、常量 | ✅ |
| `_events.py` | 核心 | SSE 事件通知中枢（含 batch-layout-done hint 队列） | ✅ |
| `_layout.py` | 核心 | 纯函数布局引擎：grid / tree / force 三策略算法 | ✅ |
| `operations.py` | 核心 | Canvas state read/write（含 per-canvas write lock）、element insertion、batch insert、save_canvas_snapshot | ✅ |
| `canvas_agent_tools.py` | 核心 | 4 个 LangChain StructuredTool：get_state / get_selection / insert_element / batch_layout | ✅ |

## 依赖

- `_events.py`: 无外部依赖（leaf utility）
- `_layout.py`: 无外部依赖（pure algorithm, leaf utility）
- `operations.py`: 依赖 `_paths.py`
- `canvas_agent_tools.py`: 依赖 `operations.py` + `_events.py` + `_layout.py`
- API 层 `api/canvas/router.py` 从 `operations.py` 导入 `get_canvas_state` / `save_canvas_snapshot`，从 `_events.py` 导入 SSE 事件 + consume_hint（正确方向：api → services）

## Agent 工具注册链路

```
frontend agent_config.enabled_builtin_tools["canvas"]
  → profile_resolver.resolve_builtin_tool_flags → enable_canvas=True
  → agent_config.canvas_id → GeneralAgentParams.canvas_id
  → tool_setup._setup_canvas_tools(tools)  # Turn1 eager when enable_canvas + canvas_id
  → factory.py: _flag_to_group includes "canvas"
  → _tool_layer_bootstrap.py: canvas_get_state, canvas_get_selection, canvas_insert_element, canvas_batch_layout → EXTENDED
```

## canvas_batch_layout 工具流程

```
LLM → canvas_batch_layout(nodes=[...], edges=[...], layout="tree")
  → _layout.py: compute_layout() 计算坐标 (<1ms)
  → operations.py: batch_insert_canvas_elements() 原子写入 snapshot.json
  → _events.py: notify_batch_layout_done() → SSE hint "batch-layout-done"
  → router.py: consume_hint → SSE event data {"hint":"batch-layout-done"}
  → CanvasWorkspace.tsx: loadStoreSnapshot + zoomToFit(animation: 400ms)
```
