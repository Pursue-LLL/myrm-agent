# settings/sections/integration 模块架构

## 架构概述

设置页「集成」域 Section 组件：凭证、外部 Agent、浏览器扩展桥、集成目录与通信渠道容器。`CommunicationSection` 以 Tab 聚合 `channels/` 子目录。

## 文件清单

| 文件 | 职责 |
|------|------|
| `ExtensionBridgeSection.tsx` | 浏览器扩展桥：WS URL 复制、Token 配置状态、扩展路径复制、Setup Guide、连接状态、授权域名、可用标签页 |
| `CredentialsSection.tsx` | 凭证管理 |
| `ExternalAgentsConfig.tsx` / `ExternalAgentAuthControls.tsx` | 外部 Agent 连接配置 |
| `OpenAIApiSection.tsx` | OpenAI 兼容 API 设置 |
| `CommunicationSection.tsx` | 渠道 Tab 容器（聚合 `channels/`） |
| `integrations/` | Integration Catalog、连接对话框、记忆绑定 |
| `channels/` | 各 IM 渠道配置卡片与路由 | [channels/_ARCH.md](channels/_ARCH.md) |

## SettingsMenu 映射（integration 组）

| Tab id | 组件 |
|--------|------|
| `extensionBridge` | `ExtensionBridgeSection` |
| `integrationCatalog` | `integrations/IntegrationCatalogSection` |
| `integrationMemory` | `integrations/IntegrationMemorySection` |
| `channels` / `channelRouting` / `voice` | `CommunicationSection`（Tauri：`channels`） |
| `openaiApi` | `OpenAIApiSection` |

`CredentialsSection` 由 `credentials` Tab 路由；`ExternalAgentsConfig` 嵌入 `system/DeveloperSection`。

## 依赖

- `@/services/extension` — 扩展桥 REST
- `@/services/channels` — 渠道配置
- `../SettingsSection.tsx`
- 父模块 [sections/_ARCH.md](../_ARCH.md)
