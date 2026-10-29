# store/config/ 模块架构

## 架构概述

WebUI 设置域的类型、LiteLLM 路由生成产物、provider 持久化 identity 迁移与 import/export 辅助。

## 文件清单

| 文件                                          | 职责                                                                                                                                                                                           | 消费者                                                                       |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `providerTypes.ts`                            | 内置 provider 定义、模型槽类型；`getLiteLLMModelName` 解析 LiteLLM 路由段：内置 id 走生成映射，自定义 provider 无映射时回落到 `providerType`（legacy 行存裸 provider id，如 `openai`），避免拼出 LiteLLM 不认识的 `custom-id/model` 路由 | Settings UI、`useProviderStore` |
| `providerIdentityMigration.ts`                | load/import 时 legacy `providerId` 一次性迁移                                                                                                                                                  | `useProviderStore.ts`、`importExport.ts`                                     |
| `subscriptionDefaultModel.ts`                 | 订阅 provider 登录后的起始模型：取 models.dev 目录中最新发布、支持工具调用且输出文本的非弃用模型，不写死模型 ID                                                                                | `providerSubscription.ts`                                                    |
| `providerSubscription.ts`                     | 订阅（OAuth）登录/登出落到 provider 状态的唯一入口：登录置 `oauthConnected`、启用 provider 并补齐起始模型、主模型槽为空时绑定；登出清标志，无其他可用认证则禁用 provider（释放其绑定的模型槽） | `useXaiDeviceLogin.ts`、`ProviderOAuthSection.tsx`、`useCredentialsOAuth.ts` |
| `visionCapability.ts`                         | 视觉能力判定与 Settings 一键推荐候选模型                                                                                                                                                       | `DefaultModelSection.tsx`、`useInputFileUpload.ts`、`AttachButton.tsx`       |
| `visionConfigGap.ts`                          | 视觉能力未配置时聊天 toast CTA（跳转 Settings 默认模型 Tab）                                                                                                                                   | `AttachButton.tsx`、`useInputFileUpload.ts`                                  |
| `litellmRouting.generated.ts`                 | 按 harness 路由表生成的 LiteLLM 路由前缀（勿手改；server 的 `test_litellm_routing_frontend_parity.py` 校验两者一致）                                                                                                                                                                | `providerTypes.ts`                                                           |
| `importExport.ts`                             | 全量 settings export/import                                                                                                                                                                    | Settings 页面                                                                |
| `searchService.ts`                            | 搜索服务 CRUD、fast/deep guard toast（`translateI18nKey` + fallback，CTA 与 `webSearchConfigGap` 同源）                                                                                        | Settings、`messageRequest`、`E2EChatBridge`                                  |
| `privacyRoutingSecret.ts`                     | 本地模型端点密钥的唯一读写入口：存进服务端加密的 `privacyRoutingSecret` 行，不放进 `personalSettings`（该行明文存放，并被审计历史与默认导出带走）；发送请求时才与路由偏好合成一次（`buildPrivacyRoutingRequest`，没有本地模型则不发送路由），不进 Zustand 状态；渐进加载下读取前先等该行同步；行不存在或没取到时每 10 秒最多向后端请求一次，同时到达的调用共用一次请求，同步失败不阻断发送，有行之后命中缓存 | `messageRequest.ts`、`usePrivacyRoutingSecret.ts` |
| `webSearchConfigGap.ts`                       | web_search 未配置 gap CTA SSOT（SSE toast + local 一键启用；i18n keys 与 searchService guard 同源）                                                                                            | `gapEvents.ts`、`searchService.ts`                                           |
| `__tests__/privacyRoutingSecret.test.ts`      | 密钥行读写（清空写空值）、读取前等待同步、已缓存不请求、缺失的行按 10 秒窗口去重、同时到达共用一次请求、加载失败不阻断且恢复后读到、没有本地模型不发送路由也不加载密钥、合成请求是副本且无密钥时不带该字段 | CI `bun run test` |
| `__tests__/webSearchConfigGap.test.ts`        | gap CTA i18n key + settings navigation                                                                                                                                                         | CI `bun run test`                                                            |
| `__tests__/providerIdentityMigration.test.ts` | 断言 migration 与 `shared/config/provider_legacy_remap.json` 一致                                                                                                                              | CI `bun run test`                                                            |
| `__tests__/visionCapability.test.ts`          | 视觉能力链判定与推荐候选选择                                                                                                                                                                   | CI `bun run test`                                                            |
| `__tests__/visionConfigGap.test.ts`           | vision config gap CTA 路径与跳转                                                                                                                                                               | CI `bun run test`                                                            |
| `__tests__/subscriptionDefaultModel.test.ts`  | 起始模型挑选：弃用/无工具调用/非文本输出被排除、按发布日期取新、日期相同按 id 稳定                                                                                                             | CI `bun run test`                                                            |
| `__tests__/providerSubscription.test.ts`      | 订阅登录/登出对真实 store 的效果：启用与起始模型、不覆盖既有选择、目录不可用时仍记为已连接、登出按其他认证决定是否禁用                                                                         | CI `bun run test`                                                            |

## 依赖

- `@shared/config/provider_legacy_remap.json` — storage id remap SSOT（见 [shared/config/_ARCH.md](../../../../shared/config/_ARCH.md)）
- `@/services/config/*` — ConfigSyncManager 持久化
