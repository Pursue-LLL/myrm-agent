# settings/mcp/

## 架构概述

MCP 服务配置 UI 子模块：列表、编辑、JSON 导入、安全扫描展示与高风险确认。

## 文件清单

| 文件 | 职责 |
|------|------|
| `MCPConfigList.tsx` | MCP 服务列表、在线状态、OAuth、安全 severity 徽章、启用时 verify loading |
| `MCPConfigEditor.tsx` | 编辑弹窗、debounce 实时扫描 findings 展示 |
| `MCPJsonImporter.tsx` | JSON 批量导入弹窗 |
| `MCPScanAckDialog.tsx` | 高风险 MCP 配置确认对话框 |
| `DeleteConfirmDialog.tsx` | 删除确认 |

## 依赖

- `hooks/useMcpSecurityGate.ts`：`gateMcpEnable` / `gateMcpConfig` / batch 统一门禁
- `hooks/useMCPConfig.ts`：配置状态、保存/启用/导入流程
- `lib/utils/mcpScanFindingText.ts`：`threat_type` 双语 + verify posture 错误 findings 解析（Editor/Ack/toast/catalog）
- `services/llm-config.ts`：`/mcp/scan`、`/mcp/scan-batch`、`/mcp/verify` API
