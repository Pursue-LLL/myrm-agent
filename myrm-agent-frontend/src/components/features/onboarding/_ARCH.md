# onboarding/ 模块架构

## 架构概述

首次启动向导：欢迎屏 → 可选外部助手迁移 → 本地能力配置 → **工具连接发现（Tools Connect）** → **可选同步目录绑定（Local）** → Smart Routing → Smart Guard → Telegram Assistant → **工作区主题选择**。

无 GPU 用户在本地能力配置阶段可通过**云端快速开始卡片**直接跳转至 `/settings/models` 配置 Gemini / SiliconFlow / OpenRouter 等含免费方案的云端 Provider，避免因无本地模型而流失。

即使用户跳过 Onboarding，`EmptyChat` 页面的 `NoProviderBanner` 也会检测到无可用 Provider 并展示引导横幅。

## 文件清单

| 文件 | 职责 |
|------|------|
| `OnboardingWizard.tsx` | 步骤编排与完成回调 |
| `ThemeOnboardingStep.tsx` | 末步：3 款内置 preset 选肤（复用 ThemePresetGrid + ConfigSync） |
| `__tests__/ThemeOnboardingStep.test.tsx` | 选肤步持久化与 Skip 行为单测 |
| `onboarding-theme-presets.ts` | 首装精选 preset id 列表 |
| `LocalCapabilitiesSetup.tsx` | 本地 Ollama/LM Studio 探测、**OpenAI-compatible Paste-URL 一步接入**（服务端 discover-models 探测 + 激活前 reachability 1-token 校验 + 原子写入 provider/default model）、SearXNG、**HardwareCookbook**（无 provider 时展示硬件推荐）、**云端快速开始卡片**（无本地模型时展示云端 Provider 引导） |
| `ToolsConnectOnboardingStep.tsx` | 工具连接发现步骤：从 Catalog API 拉取精选服务（GitHub/Notion/Gmail/Slack/Linear），复用 IntegrationConnectDialog 完成连接，失败时静默跳过 |
| `SmartRoutingStep.tsx` | Smart Routing 引导步骤：自动检测已配置模型并分类为 lite/standard/reasoning 三档，展示预估节省比例，一键启用或跳过 |
| `SmartGuardStep.tsx` | Smart Intent Guard 引导步骤：默认启用 + 轻量模型智能预选（优先 mini/flash/haiku 等低成本模型），通过 ConfigSyncManager 写入 securityConfig |
| `TelegramAssistantOnboardingStep.tsx` | Telegram 助手一键接入步骤 |
| `SyncFolderOnboardingStep.tsx` | Local 可选步骤：复用 `MigrationVaultBindPanel`；消费 migration workspace bind 候选预填；bind 后 handoff projectId |

## 依赖

- `@/components/features/settings/model-service/HardwareCookbook` — 硬件模型推荐（Settings 与 Onboarding 共用）
- `@/components/features/settings/default-model/EnabledModelSelect` — 模型选择器（Settings 与 Onboarding 共用）
- `@/components/features/settings/sections/integration/integrations/IntegrationConnectDialog` — 集成连接对话框（Settings 与 Onboarding 共用）
- `@/components/features/settings/sections/integration/integrations/service-icons` — 服务品牌图标
- `@/services/config` — ConfigSyncManager 持久化配置
- `@/services/onboarding` — readiness 状态
- `@/services/channels` — Telegram 凭据配置探测（判断是否展示 Telegram onboarding step）
- `@/components/features/chat-window/NoProviderBanner` — EmptyChat 未配置 Provider 引导横幅
