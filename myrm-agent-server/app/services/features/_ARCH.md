# services/features 模块架构


## 架构概述

Feature Flags 服务层。提供功能开关注册、状态查询和用户覆盖配置持久化。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 | — |
| `registration.py` | 核心 | Feature Flag 注册（定义所有可用功能开关：8 stable + 7 experimental） | ✅ |
| `feature_config_service.py` | 核心 | 用户级功能配置持久化服务 | ✅ |

## 门控执行点

| FeatureSpec | 后端门控 | 前端门控 |
|-------------|---------|---------|
| goals_system | `api/goals/router.py` verify_goals_enabled | GoalModeToggle |
| companion_mode | `api/companion/router.py` verify_companion_enabled | SettingsMenu / EmptyChat |
| deep_research | `orchestrator.py` action_mode gate | SearchModeSelector featureGate |
| consensus | `orchestrator.py` action_mode gate | SearchModeSelector featureGate |
| voice_interaction | `api/voice,stt,tts` verify_voice_enabled | MessageInput isVoiceEnabled |
