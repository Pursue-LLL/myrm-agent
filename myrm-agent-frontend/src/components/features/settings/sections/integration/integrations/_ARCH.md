# settings/sections/integration/integrations/ 模块架构

## 架构概述

Settings「Integration」下的第三方集成目录：OAuth 连接、Catalog 浏览与集成记忆。

## 文件清单

| 文件 | 职责 |
|------|------|
| `IntegrationCatalogSection.tsx` | 集成服务目录与连接状态 |
| `IntegrationConnectDialog.tsx` | OAuth / API Key 连接对话框；消费 probe `shouldBlockConnect`、`reasonCode` 与 `recommendedMode`，在失败态提供本地化诊断与可执行下一步动作（重试成功后自动续接连接；`local_or_tauri` 打开本地部署指引并引导切换模式）；`probeUrl` 缺失时回退 `mcpConfig.url`，避免探测语义死路 |
| `deploymentGuard.ts` | 连接前部署模式守卫：在 cloud/sandbox 下阻断 local-only 条目（含无 probeUrl 兜底） |
| `deploymentGuard.test.ts` | 部署守卫单测：覆盖 cloud_not_supported 在 sandbox/local-only 下的阻断决策 |
| `IntegrationConnectDialog.test.tsx` | Dialog 行为级单测：覆盖无 probeUrl 兜底阻断、probe `shouldBlockConnect=true` 阻断、`reasonCode` 文案分流，以及 `recommendedMode` 三分支动作闭环（`start_local_editor_mcp` / `verify_local_network_and_editor` 重试后自动续接连接，`local_or_tauri` 打开本地部署指引） |
| `IntegrationMemorySection.tsx` | 集成相关记忆设置 |
| `catalog-types.ts` | Catalog 类型定义 |
| `catalog-icons.tsx` | Catalog 图标映射 |
| `service-icons.tsx` | 服务品牌图标 |

## 依赖

- [integration/_ARCH.md](../_ARCH.md)
- `@/services/integrations` — 集成 REST 客户端
