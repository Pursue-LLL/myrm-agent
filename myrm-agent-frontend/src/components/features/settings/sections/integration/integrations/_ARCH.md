# settings/sections/integration/integrations/ 模块架构

## 架构概述

Settings「Integration」下的第三方集成目录：OAuth 连接、Catalog 浏览与集成记忆。

## 文件清单

| 文件 | 职责 |
|------|------|
| `IntegrationCatalogSection.tsx` | 集成服务目录与连接状态 |
| `IntegrationConnectDialog.tsx` | OAuth / API Key 连接对话框；消费 probe `shouldBlockConnect` 语义并执行 cloud/local-only 阻断 |
| `deploymentGuard.ts` | 连接前部署模式守卫：在 cloud/sandbox 下阻断 local-only 条目（含无 probeUrl 兜底） |
| `deploymentGuard.test.ts` | 部署守卫单测：覆盖 cloud_not_supported 在 sandbox/local-only 下的阻断决策 |
| `IntegrationConnectDialog.test.tsx` | Dialog 行为级单测：覆盖无 probeUrl 兜底阻断与 probe `shouldBlockConnect=true` 阻断链路 |
| `IntegrationMemorySection.tsx` | 集成相关记忆设置 |
| `catalog-types.ts` | Catalog 类型定义 |
| `catalog-icons.tsx` | Catalog 图标映射 |
| `service-icons.tsx` | 服务品牌图标 |

## 依赖

- [integration/_ARCH.md](../_ARCH.md)
- `@/services/integrations` — 集成 REST 客户端
