# lib/utils/

通用纯函数工具集（认证头、导出、剪贴板、Agent 映射等）。**无** React 组件。

按域单文件组织；新工具优先就近放 feature/lib 子目录，仅跨 3+ feature 复用才放此处。

子目录 `__tests__/` 覆盖高价值纯函数。

- `localeUtils.ts`：Locale 工具集 — cookie 常量、客户端读取、后端格式映射、营销参数解析、RFC 7231 Accept-Language 协商。
- `responseLocalePolicy.ts`：Agent `engine_params.response_locale_policy` 读写（正式韩语 Switch ↔ harness suffix SSOT）。
- `mcpConfigNormalizer.ts`：MCP transport/keepalive 语义归一化（`http` → `streamable_http`；`stdio` keepalive 清空）。
- `subagentTree.ts`：Subagent 树数据工具 — 构建树、子树聚合（成本/tokens/后代）、全局统计、排序（spawn/busiest/slowest/status）、过滤（all/running/failed/leaf）、展平、格式化（fmtCost/fmtTokens/fmtBudgetCost）、预算/用量提取（extractCostUsd/extractTotalTokens/extractBudgetTokens/extractMaxCostUsd，成本经 `token_usage.total_cost_usd`，上限经 `budget.max_cost_usd`/`budget.budget_tokens`）。
- `taskTopologyModel.ts`：任务拓扑数据模型 — 纯函数把 subagent 树 / fission 拓扑转为 ReactFlow 可渲染图模型（buildTopologyModel / buildFissionTopologyModel / buildMergedTopologyModel：节点/边/墓碑/焦点/进度/元数据、悬空边过滤、label 截断、状态 tone 映射；**验证失败节点 tone 降级为 danger 并透传 verification 字段**；fission 命名空间按 fission_id 隔离）。
