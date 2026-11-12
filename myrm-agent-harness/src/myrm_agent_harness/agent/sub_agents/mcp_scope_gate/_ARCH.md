# mcp_scope_gate/

## 架构概述

数字员工 / Agent 作用域 MCP 门禁（Employee/Agent-Scoped MCP Tool Discovery Gate）：按 `agent_id` 限制一个 Agent 可发现、可调用的 MCP Server 与工具。
1. **显式策略**：`EmployeeToolScopePolicy` 为某个 `agent_id` 声明 `allowed_mcp_servers` 与按 Server 划分的 `tool_allowlist_map`（某个 Server 没有列出工具白名单或白名单为空，表示放行该 Server 的全部工具）。策略由宿主调用 `EmployeeScopedMcpDiscoveryGate.register_policy` 注册，存放在进程内存、线程安全的注册表里，不落盘，进程重启后需要重新注册；
2. **发现过滤（Fail-Closed）**：`filter_discovered_tools` 把动态发现的候选工具拆成放行与拦截两组：Agent 没有已注册策略时全部拦截，Server 不在 `allowed_mcp_servers` 内、或工具不在该 Server 的白名单内时拦截对应工具；
3. **调用时校验**：`verify_tool_invocation` 对单个 `(server, tool)` 复用同一套判定，拦截时抛出 `EmployeeToolScopeViolationError`。PTC 的 MCP IPC 路径里，`skills/mcp/ipc_request_policy.scope_gate_error` 是 `REQUEST_GATES` 中的一道门，`MCPIPCServer` 对每个请求按序执行；它使用服务端启动时由宿主固定的 `CallerScope.agent_id`（`prepare_mixin` 取自 `get_agent_id()`，与会话 ID 分离，请求自身无法改写），仅当该 `agent_id` 存在且已注册策略时才校验，越权请求以 `Agent scope violation: …` 拒绝；没有 `agent_id` 或没有已注册策略的 Agent 不受这道门限制，其余请求门照常生效。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 统一导出数字员工 MCP 作用域门禁与领域类型 | ✅ |
| `types.py` | 核心 | 员工作用域策略、过滤判定结果与越权异常契约 | ✅ |
| `scope_gate.py` | 核心 | 线程安全策略注册、动态发现工具裁剪与调用权限门禁校验器 | ✅ |
