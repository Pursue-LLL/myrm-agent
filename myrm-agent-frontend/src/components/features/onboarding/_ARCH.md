# onboarding/ 模块架构

## 架构概述

首次启动向导：欢迎屏 → 可选外部助手迁移 → 本地能力配置（模型 + OpenAI-compatible Paste-URL 向导 + 搜索 + HardwareCookbook + 云端快速开始） → 条件性 Smart Routing 引导（≥2 模型且未启用时展示）。

无 GPU 用户在本地能力配置阶段可通过**云端快速开始卡片**直接跳转至 `/settings/models` 配置 Gemini / SiliconFlow / OpenRouter 等含免费方案的云端 Provider，避免因无本地模型而流失。

即使用户跳过 Onboarding，`EmptyChat` 页面的 `NoProviderBanner` 也会检测到无可用 Provider 并展示引导横幅。

## 文件清单

| 文件 | 职责 |
|------|------|
| `OnboardingWizard.tsx` | 步骤编排与完成回调 |
| `LocalCapabilitiesSetup.tsx` | 本地 Ollama/LM Studio 探测、**OpenAI-compatible Paste-URL 一步接入**（服务端 discover-models 探测 + 原子写入 provider/default model）、SearXNG、**HardwareCookbook**（无 provider 时展示硬件推荐）、**云端快速开始卡片**（无本地模型时展示云端 Provider 引导） |
| `SmartRoutingStep.tsx` | Smart Routing 引导步骤：自动检测已配置模型并分类为 lite/standard/reasoning 三档，展示预估节省比例，一键启用或跳过 |

## 依赖

- `@/components/features/settings/model-service/HardwareCookbook` — 硬件模型推荐（Settings 与 Onboarding 共用）
- `@/services/onboarding` — readiness 状态
- `@/components/features/chat-window/NoProviderBanner` — EmptyChat 未配置 Provider 引导横幅
