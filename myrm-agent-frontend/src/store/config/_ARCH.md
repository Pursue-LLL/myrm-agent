# store/config/ 模块架构

## 架构概述

WebUI 设置域的类型、LiteLLM 路由生成产物、provider 持久化 identity 迁移与 import/export 辅助。

## 文件清单

| 文件                                          | 职责                                                                                                                                                                                           | 消费者                                                                       |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `providerTypes.ts`                            | 内置 provider 定义、模型槽类型                                                                                                                                                                 | Settings UI、`useProviderStore`                                              |
| `providerIdentityMigration.ts`                | load/import 时 legacy `providerId` 一次性迁移                                                                                                                                                  | `useProviderStore.ts`、`importExport.ts`                                     |
| `subscriptionDefaultModel.ts`                 | 订阅 provider 登录后的起始模型：取 models.dev 目录中最新发布、支持工具调用且输出文本的非弃用模型，不写死模型 ID                                                                                | `providerSubscription.ts`                                                    |
| `providerSubscription.ts`                     | 订阅（OAuth）登录/登出落到 provider 状态的唯一入口：登录置 `oauthConnected`、启用 provider 并补齐起始模型、主模型槽为空时绑定；登出清标志，无其他可用认证则禁用 provider（释放其绑定的模型槽） | `useXaiDeviceLogin.ts`、`ProviderOAuthSection.tsx`、`useCredentialsOAuth.ts` |
| `visionCapability.ts`                         | 视觉能力判定与 Settings 一键推荐候选模型                                                                                                                                                       | `DefaultModelSection.tsx`、`useInputFileUpload.ts`、`AttachButton.tsx`       |
| `visionConfigGap.ts`                          | 视觉能力未配置时聊天 toast CTA（跳转 Settings 默认模型 Tab）                                                                                                                                   | `AttachButton.tsx`、`useInputFileUpload.ts`                                  |
| `litellmRouting.generated.ts`                 | harness 生成的 LiteLLM 路由前缀                                                                                                                                                                | `providerTypes.ts`                                                           |
| `importExport.ts`                             | 全量 settings export/import                                                                                                                                                                    | Settings 页面                                                                |
| `searchService.ts`                            | 搜索服务 CRUD、fast/deep guard toast（`translateI18nKey` + fallback，CTA 与 `webSearchConfigGap` 同源）                                                                                        | Settings、`messageRequest`、`E2EChatBridge`                                  |
| `webSearchConfigGap.ts`                       | web_search 未配置 gap CTA SSOT（SSE toast + local 一键启用；i18n keys 与 searchService guard 同源）                                                                                            | `gapEvents.ts`、`searchService.ts`                                           |
| `__tests__/webSearchConfigGap.test.ts`        | gap CTA i18n key + settings navigation                                                                                                                                                         | CI `bun run test`                                                            |
| `__tests__/providerIdentityMigration.test.ts` | 断言 migration 与 `shared/config/provider_legacy_remap.json` 一致                                                                                                                              | CI `bun run test`                                                            |
| `__tests__/visionCapability.test.ts`          | 视觉能力链判定与推荐候选选择                                                                                                                                                                   | CI `bun run test`                                                            |
| `__tests__/visionConfigGap.test.ts`           | vision config gap CTA 路径与跳转                                                                                                                                                               | CI `bun run test`                                                            |
| `__tests__/subscriptionDefaultModel.test.ts`  | 起始模型挑选：弃用/无工具调用/非文本输出被排除、按发布日期取新、日期相同按 id 稳定                                                                                                             | CI `bun run test`                                                            |
| `__tests__/providerSubscription.test.ts`      | 订阅登录/登出对真实 store 的效果：启用与起始模型、不覆盖既有选择、目录不可用时仍记为已连接、登出按其他认证决定是否禁用                                                                         | CI `bun run test`                                                            |

## 依赖

- `@shared/config/provider_legacy_remap.json` — storage id remap SSOT（见 [shared/config/_ARCH.md](../../../../shared/config/_ARCH.md)）
- `@/services/config/*` — ConfigSyncManager 持久化
