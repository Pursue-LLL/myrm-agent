# settings/mcp/

## 架构概述

MCP 服务配置 UI 子模块：列表、编辑、JSON 导入、注册中心浏览与安装、安全扫描展示与高风险确认。

## 文件清单

| 文件 | 职责 |
|------|------|
| `MCPConfigList.tsx` | MCP 服务列表、在线状态、OAuth、安全 severity 徽章、启用时 verify loading |
| `MCPConfigEditor.tsx` | 编辑弹窗、`hostSerial`（state-aware serial mode）开关、`keepaliveInterval` 输入（remote transport，最小 5 秒校验）、debounce 实时扫描 findings 展示 |
| `MCPJsonImporter.tsx` | JSON 批量导入弹窗 |
| `MCPScanAckDialog.tsx` | 高风险 MCP 配置确认对话框 |
| `DeleteConfirmDialog.tsx` | 删除确认 |
| `MCPRegistryBrowser.tsx` | 注册中心浏览器：搜索（防抖 300ms）+ 分页加载 + 已安装过滤 |
| `MCPRegistryCard.tsx` | 注册中心服务卡片：图标/名称/描述/安装数/作者/安装按钮 |
| `MCPInstallWizard.tsx` | 安装向导：详情加载 → 环境变量表单（敏感字段密码框）→ 传输协议检测 → 安全扫描确认 |

## 依赖

- `hooks/useMcpSecurityGate.ts`：`gateMcpEnable` / `gateMcpConfig` / batch 统一门禁
- `hooks/useMCPConfig.ts`：配置状态、保存/启用/导入流程
- `lib/utils/mcpScanFindingText.ts`：`threat_type` 双语 + verify posture 错误 findings 解析（Editor/Ack/toast/catalog）
- `services/llm-config.ts`：`/integrations/mcp/scan`、`/integrations/mcp/scan-batch`、`/integrations/mcp/verify`、`/integrations/mcp/registry/search`、`/integrations/mcp/registry/detail`、`/integrations/mcp/oauth/*` API
