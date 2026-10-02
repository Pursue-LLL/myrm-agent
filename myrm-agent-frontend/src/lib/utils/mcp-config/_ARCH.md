# lib/utils/mcp-config/

MCP 配置域子包：transport/keepalive 语义归一化、JSON 配置解析与扫描 finding 文案。**无** React 组件，全部纯函数。

对外唯一门面为 `index.ts` barrel（`@/lib/utils/mcp-config`）；组件层消费点一律经 barrel 取公开符号，不深路径引用内部构件。

`__tests__/` 覆盖归一化与解析行为。

- `index.ts`：域门面 barrel — 显式导出清单聚合三文件公开符号，组件层统一导入入口；新增导出须同步本清单（漏加即 typecheck 断裂，编译器护栏）。
- `mcpConfigNormalizer.ts`：MCP 配置语义归一化 — transport 规范化（`http` → `streamable_http`）、keepalive 语义清零（`stdio` 无 keepalive）与单条/批量服务配置归一。
- `mcpConfigParser.ts`：MCP 配置解析器 — JSON 文本到 MCPServiceConfig 解析（parseMCPConfigsFromJSON / parseServerConfig），transport/keepalive 经包内 `mcpConfigNormalizer.ts` 归一。
- `mcpScanFindingText.ts`：MCP 扫描 finding 文案 — finding 字段/描述/建议/阻断消息格式化与 API 错误详情解析（parseMcpFindingsFromApiErrorDetails）。

## 依赖

- `@/store/config/types`（POS: 配置类型定义）— MCPServiceConfig / MCPScanFinding 类型。
