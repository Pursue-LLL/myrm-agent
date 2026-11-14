# services/features 模块架构


## 架构概述

Feature Flags 服务层。提供功能开关注册、状态查询和用户覆盖配置持久化。

## Consensus（独立 action mode）产品面状态

> 没有独立的 Consensus 模式；MoA 能力通过 Agent 模式 + 模型 picker overlay 提供。

| 项 | 当前状态 | SSOT |
|---|---|---|
| Feature Flag `consensus` | `FeatureStage.REMOVED` | `registration.py` |
| SearchModeSelector「Consensus」 | 不提供 | `SearchModeSelector.tsx` |
| 历史 overrides 中 `consensus: true` | `sanitize_user_overrides()` 清除 | `product_surface.py` |
| legacy `action_mode=consensus` API | 400 + DB migrate → `agent` | `orchestrator.py` |
| Harness `consensus/` engine | 保留（MoA overlay middleware 依赖） | harness |

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
| consensus | **REMOVED**；legacy API shim → MoA overlay | 已从 SearchModeSelector 移除 |
| voice_interaction | `api/voice,stt,tts` verify_voice_enabled | MessageInput isVoiceEnabled |
