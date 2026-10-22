# Conversational Studio & Zero-CLI Architecture

## 职责边界
- `conversationalOnboardingTypes.ts`: 对话式向导步骤、领域配方、推荐技能及启动状态强契约；
- `conversationalInferenceEngine.ts`: 纯函数自然语言推导引擎，提供基于意图关键词与预置配方的精准角色与技能映射；
- `useConversationalOnboardingStore.ts`: Zustand 状态总线，管理问答流式消息、动态配方组装、技能开关与生效入库；
- `ConversationalOnboardingWizard.tsx`: “先聊起来、边聊边配”沉浸式向导组件，左侧交互式会话流，右侧实时配方微调与一键激活；
- `ZeroCliQuickLauncherDeck.tsx`: 零命令行图形化启动甲板，替代传统终端提示，提供环境探活指标与快捷任务启动卡片。
