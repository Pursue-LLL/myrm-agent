# hooks/settings/

Settings 域状态：系统/个人/MCP 配置与安全门禁。

| 文件                        | 职责                          |
| --------------------------- | ----------------------------- |
| `useSystemConfig.ts`        | 系统配置 load/save/reset      |
| `usePersonalSettings.ts`    | 个人偏好                      |
| `usePrivacyRoutingSecret.ts` | 本地模型端点密钥：读自独立的加密配置行，与路由偏好分开存取；首次读取等该行同步，用户在此之前已输入的内容不被加载结果覆盖，跟随其它标签页的变更 |
| `useMCPConfig.ts`           | MCP 配置状态、并行连通性验证与保存/启用/删除流程 |
| `mcpConfigHelpers.ts`       | MCP 表单默认值、双语导入模板、参数解析与字段校验纯函数 |
| `useMcpSecurityGate.ts`     | MCP enable/config 安全门禁    |
| `useSettingsSubTabUrl.ts`   | Settings 子 tab URL 同步      |
| `useConfigErrorDetector.ts` | 配置错误检测                  |

消费者：`components/features/settings/`。
