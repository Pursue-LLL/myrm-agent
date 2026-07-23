# store/config/ 模块架构

## 架构概述

WebUI 设置域的类型、LiteLLM 路由生成产物、provider 持久化 identity 迁移与 import/export 辅助。

## 文件清单

| 文件 | 职责 | 消费者 |
|------|------|--------|
| `providerTypes.ts` | 内置 provider 定义、模型槽类型 | Settings UI、`useProviderStore` |
| `providerIdentityMigration.ts` | load/import 时 legacy `providerId` 一次性迁移 | `useProviderStore.ts`、`importExport.ts` |
| `litellmRouting.generated.ts` | harness 生成的 LiteLLM 路由前缀 | `providerTypes.ts` |
| `importExport.ts` | 全量 settings export/import | Settings 页面 |
| `searchService.ts` | 搜索服务 CRUD、fast/deep guard toast | Settings、`messageRequest` |
| `webSearchConfigGap.ts` | web_search 未配置 gap CTA SSOT（SSE toast + local 一键启用；i18n keys 与 searchService guard 同源） | `gapEvents.ts`、`searchService.ts` |
| `__tests__/webSearchConfigGap.test.ts` | gap CTA i18n key + settings navigation | CI `bun run test` |
| `__tests__/providerIdentityMigration.test.ts` | 断言 migration 与 `shared/config/provider_legacy_remap.json` 一致 | CI `bun run test` |

## 依赖

- `@shared/config/provider_legacy_remap.json` — storage id remap SSOT（见 [shared/config/_ARCH.md](../../../shared/config/_ARCH.md)）
- `@/services/config/*` — ConfigSyncManager 持久化
