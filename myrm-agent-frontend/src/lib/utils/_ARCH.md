# lib/utils/

通用纯函数工具集（认证头、导出、剪贴板、Agent 映射等）。**无** React 组件。

按域单文件组织；新工具优先就近放 feature/lib 子目录，仅跨 3+ feature 复用才放此处。

子目录 `__tests__/` 覆盖高价值纯函数。

- `localeUtils.ts`：Locale 工具集 — cookie 常量、客户端读取、后端格式映射、营销参数解析、RFC 7231 Accept-Language 协商。
- `mcpConfigNormalizer.ts`：MCP transport/keepalive 语义归一化（`http` → `streamable_http`；`stdio` keepalive 清空）。
- `subagentTree.ts`：Subagent 树数据工具 — 构建树、子树聚合（成本/tokens/后代）、全局统计、排序（spawn/busiest/slowest/status）、过滤（all/running/failed/leaf）、展平、格式化（fmtCost/fmtTokens）。
