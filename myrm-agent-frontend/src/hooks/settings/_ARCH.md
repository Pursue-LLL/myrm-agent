# hooks/settings/

Settings 域状态：系统/个人/MCP 配置与安全门禁。

| 文件                        | 职责                          |
| --------------------------- | ----------------------------- |
| `useSystemConfig.ts`        | 系统配置 load/save/reset      |
| `usePersonalSettings.ts`    | 个人偏好                      |
| `useMCPConfig.ts`           | MCP 配置状态、并行连通性验证与保存/启用/删除流程 |
| `mcpConfigHelpers.ts`       | MCP 表单默认值、双语导入模板、参数解析与字段校验纯函数 |
| `useMcpSecurityGate.ts`     | MCP enable/config 安全门禁    |
| `useSettingsSubTabUrl.ts`   | Settings 子 tab URL 同步      |
| `useConfigErrorDetector.ts` | 配置错误检测                  |

消费者：`components/features/settings/`。
