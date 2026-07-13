# services/features 模块架构


## 架构概述

Feature Flags 服务层。提供功能开关注册、状态查询和用户覆盖配置持久化。

## 深度研究（Deep Research）产品面状态

> **当前：全产品面禁用 / 隐藏。未来：计划正式上线。**

Harness 层 `deep_research` 编排器仍保留（`myrm-agent-harness/agent/deep_research/`），但 **Server + Frontend 产品入口已关闭**：

| 项 | 当前状态 | SSOT |
|---|---|---|
| Feature Flag `deep_research` | `FeatureStage.REMOVED`（不可 toggle、不可 override 启用） | `registration.py` |
| 模式选择器「深度研究」 | 已移除 | `SearchModeSelector.tsx` |
| 内置 Agent `builtin-researcher` / `builtin-deep-search` | API 列表与画廊隐藏 | `product_surface.py` |
| 预置模板 `research_analysis_squad` | 模板 API 隐藏 | `product_surface.py` |
| 历史 `user_overrides.json` 中的 `deep_research: true` | 启动时 `sanitize_user_overrides()` 自动清除 | `feature_config_service.py` |
| 直调 `action_mode=deep_research` | orchestrator 403 Feature Gate | `orchestrator.py` |

**未来上线 checklist**（开发者备忘，非本次任务）：

1. `registration.py`：将 `deep_research` 改回 `EXPERIMENTAL` 或 `STABLE`
2. `product_surface.py`：从 `HIDDEN_*` / `REMOVED_FEATURE_OVERRIDE_KEYS` 移除对应项
3. `SearchModeSelector.tsx`：恢复 `deep_research` 模式入口
4. 更新本段文档状态为「已上线」

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 | — |
| `registration.py` | 核心 | Feature Flag 注册（定义所有可用功能开关） | ✅ |
| `feature_config_service.py` | 核心 | 用户级功能配置持久化 + REMOVED feature override 自动净化 | ✅ |
| `product_surface.py` | 核心 | 隐藏 Agent/模板/已移除 Feature 的产品面 SSOT | ✅ |

## 门控执行点

| FeatureSpec | 后端门控 | 前端门控 |
|-------------|---------|---------|
| goals_system | `api/goals/router.py` verify_goals_enabled | GoalModeToggle |
| companion_mode | `api/companion/router.py` verify_companion_enabled | SettingsMenu / EmptyChat |
| deep_research | `orchestrator.py` action_mode gate（**REMOVED，永久 off**） | 已从 SearchModeSelector 移除 |
| consensus | `orchestrator.py` action_mode gate | SearchModeSelector featureGate |
| voice_interaction | `api/voice,stt,tts` verify_voice_enabled | MessageInput isVoiceEnabled |
