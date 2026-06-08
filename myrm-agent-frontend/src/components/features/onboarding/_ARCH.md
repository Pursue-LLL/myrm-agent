# onboarding/ 模块架构

## 架构概述

首次启动向导：欢迎屏 → 可选竞品迁移 → 本地能力配置（模型 + 搜索 + Hardware Cookbook）。

## 文件清单

| 文件 | 职责 |
|------|------|
| `OnboardingWizard.tsx` | 步骤编排与完成回调 |
| `LocalCapabilitiesSetup.tsx` | 本地 Ollama/LM Studio 探测、SearXNG、**HardwareCookbook**（无 provider 时展示硬件推荐） |

## 依赖

- `@/components/features/settings/model-service/HardwareCookbook` — 硬件模型推荐（Settings 与 Onboarding 共用）
- `@/services/onboarding` — readiness 状态
