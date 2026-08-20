# hooks/settings/

Settings 域状态：系统/个人/MCP 配置与安全门禁。

| 文件                        | 职责                          |
| --------------------------- | ----------------------------- |
| `useSystemConfig.ts`        | 系统配置 load/save/reset      |
| `usePersonalSettings.ts`    | 个人偏好                      |
| `useMCPConfig.ts`           | MCP 传输/hostSerial/keepalive |
| `useMcpSecurityGate.ts`     | MCP enable/config 安全门禁    |
| `useSettingsSubTabUrl.ts`   | Settings 子 tab URL 同步      |
| `useConfigValidation.ts`    | 配置校验                      |
| `useConfigErrorDetector.ts` | 配置错误检测                  |

消费者：`components/features/settings/`。
