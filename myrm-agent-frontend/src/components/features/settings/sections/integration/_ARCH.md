# settings/sections/integration 模块架构

## 架构概述

设置页「集成」域 Section 组件：凭证、外部 Agent 连接、浏览器扩展桥、集成目录与通信渠道容器。`CommunicationSection` 以 Tab 聚合 `channels/` 子目录。

## 文件清单

| 文件                                                         | 地位                                                                           | 职责                                          | I/O/P |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------ | --------------------------------------------- | ----- |
| `ConnectSection.tsx`                                         | 核心                                                                           | Connect Wizard                                | ✅    |
| `ExtensionBridgeSection.tsx`                                 | 核心                                                                           | 浏览器扩展桥 UI                               | ✅    |
| `extension/ExtensionClipAgentField.tsx`                      | 组件                                                                           | Wiki 剪藏目标 Agent 下拉                      | ✅    |
| `extension/`                                                 | 子模块                                                                         | 见 [`extension/_ARCH.md`](extension/_ARCH.md) | ✅    |
| `CredentialsSection.tsx`                                     | re-export                                                                      | 凭证管理                                      | —     |
| `credentials/`                                               | Vault / 文件 / OAuth 凭证子模块 · [credentials/_ARCH.md](credentials/_ARCH.md) |
| `ExternalAgentsConfig.tsx` / `ExternalAgentAuthControls.tsx` | 外部 Agent 连接配置                                                            |
| `OpenAIApiSection.tsx`                                       | Agent API 设置（OpenAI 兼容端点，仅 Agent 执行）                               |
| `CommunicationSection.tsx`                                   | 渠道 Tab 容器（聚合 `channels/`）                                              |
| `integrations/`                                              | Integration Catalog、Lifecycle Webhooks、连接对话框、记忆绑定                  |
| `channels/`                                                  | 各 IM 渠道配置卡片与路由                                                       | [channels/_ARCH.md](channels/_ARCH.md)        |

## 路由 SSOT（Settings Tab）

`extensionBridge` / `connect` 等 Tab 须在三处登记，缺一即 404、编译报错或被 i18n 校验拦截：

| 登记点                                                                      | 文件                                                                        |
| --------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Tab id `SETTINGS_TABS`（page、Layout、Menu、脏状态 store 共读，缺失即 404） | `settingsRoutes.ts`                                                         |
| 布局 `SECTION_COMPONENTS`（对 `SettingsTab` 穷尽，缺失即编译报错）          | `SettingsLayout.tsx`                                                        |
| 侧栏 `SettingsMenu` + `locales/*` 的 `metadata.settingsTabs` / `settings.menu` | `SettingsMenu.tsx` · `scripts/verify-i18n.mjs`（从 `settingsRoutes.ts` 读取） |

## SettingsMenu 映射（integration 组）

| Tab id                                  | 组件                                        |
| --------------------------------------- | ------------------------------------------- |
| `connect`                               | `ConnectSection`                            |
| `extensionBridge`                       | `ExtensionBridgeSection`                    |
| `integrationCatalog`                    | `integrations/IntegrationCatalogSection`    |
| `integrationMemory`                     | `integrations/IntegrationMemorySection`     |
| `channels` / `channelRouting` / `voice` | `CommunicationSection`（Tauri：`channels`） |
| `openaiApi`                             | `OpenAIApiSection`                          |

`CredentialsSection` 由 `credentials` Tab 路由；`ExternalAgentsConfig` 嵌入 `system/DeveloperSection`。

## 依赖

- `@/hooks/extension/useExtensionWebUiOriginSeed` — App mount 写入 clip `web_ui_origin`
- `@/services/connect` — Connect Wizard REST
- `@/services/extension` — 扩展桥 REST
- `@/services/channels` — 渠道配置
- `../SettingsSection.tsx`
- 父模块 [sections/_ARCH.md](../_ARCH.md)
