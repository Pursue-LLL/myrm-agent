# onboarding/ 模块架构

## 架构概述

云沙箱首次启动向导：欢迎屏 → 外部助手迁移（首屏，含「从备份恢复」与「立即开始」） → **工具连接发现（Tools Connect）** → **首检 Doctor（模型/后端/配额）** → Smart Routing（启用 ≥2 个模型且未开启路由时）→ Smart Guard（有启用模型且未开启自动审查时）→ **工作区主题选择**。

向导只在沙箱出现（`PageLayout` 以 `isSandbox()` 门控）：本地与桌面安装直接进入首页，未配置 Provider 时由 `EmptyChat` 的 `NoProviderBanner` 提示，模型、搜索、Telegram 等在 Settings 对应页配置。

## 文件清单

| 文件                                     | 职责                                                                                                                                                                                                                                                                                         |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `OnboardingWizard.tsx`                   | 沙箱向导的步骤编排与完成回调；欢迎屏停留至少 2.5 秒且 Provider store 已初始化；首屏（迁移步）下方挂「从备份恢复」入口，只出现一次 |
| `FirstRunDoctorCard.tsx`                 | 首检 Doctor 聚合卡：模型/后端/配额只读探针 + 一键修深链（无登录凭证时配额行视为通过） |
| `ThemeOnboardingStep.tsx`                | 末步：3 款内置 preset 选肤（复用 ThemePresetGrid + ConfigSync）                                                                                                                                                                                                                              |
| `__tests__/ThemeOnboardingStep.test.tsx` | 选肤步持久化与 Skip 行为单测                                                                                                                                                                                                                                                                 |
| `onboarding-theme-presets.ts`            | 首装精选 preset id 列表                                                                                                                                                                                                                                                                      |
| `ToolsConnectOnboardingStep.tsx`         | 工具连接发现步骤：从 Catalog API 拉取精选服务（GitHub/Notion/Microsoft To Do/Slack/Linear），复用 IntegrationConnectDialog 完成连接，连接状态与目录卡片共用 `catalog-connection` / `CatalogConnectionStatus`（进入本步骤前就已连接的服务同样显示已连接并可继续；已停用不计为已连接），失败时静默跳过 |
| `SmartRoutingStep.tsx`                   | Smart Routing 引导步骤：复用 `isReasoningModelByName` 权威 SSOT 与来源拓扑感知，自动检测已配置模型并分类为 lite/standard/reasoning 三档，展示预估节省比例，一键启用或跳过                                                                                                                    |
| `__tests__/SmartRoutingStep.test.tsx`    | Smart Routing 引导步骤单测：覆盖 `deepseek-reasoner`、Gemini 思考模型分类与开闭源混合协同启发式推荐                                                                                                                                                                                          |
| `SmartGuardStep.tsx`                     | Smart Intent Guard 引导步骤：默认启用 + 轻量模型智能预选（优先 mini/flash/haiku 等低成本模型），通过 ConfigSyncManager 写入 securityConfig                                                                                                                                                   |

## 依赖

- `@/components/features/settings/default-model/EnabledModelSelect` — 模型选择器（Settings 与 Onboarding 共用）
- `@/components/features/settings/sections/integration/integrations/IntegrationConnectDialog` — 集成连接对话框（Settings 与 Onboarding 共用）
- `@/components/features/settings/sections/integration/integrations/catalog-connection` / `catalog-locale` / `CatalogConnectionStatus` — 目录连接状态、文案语言与状态标签（Settings 目录与 Onboarding 共用）
- `@/components/features/settings/sections/integration/integrations/service-icons` — 服务品牌图标
- `@/services/config` — ConfigSyncManager 持久化配置
- `@/services/onboarding` — readiness 状态
- `@/components/features/chat-window/NoProviderBanner` — EmptyChat 未配置 Provider 引导横幅
- `@/components/features/instance-archive/RestoreEntry` — 首屏「从备份恢复」入口（部署形态不支持备份时自行隐藏）
