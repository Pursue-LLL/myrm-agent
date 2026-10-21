# Adaptive Thinking Budget Toggle & Inline Reasoning Timeline Architecture

## Overview
自适应思考预算切换、内联推理阶段时间轴与思考状态展开/折叠套件，包含：
- `thinkingBudgetTypes.ts`: 思考预算 4 档契约（off / low 1k / medium 8k / high 32k）、阶段里程碑与收纳盒状态；
- `reasoningTimelineEngine.ts`: 预算配置字典、思维链自然段/章节智能切片算法、耗时与 Token 格式化引擎；
- `useThinkingBudgetStore.ts`: Zustand 状态管理，驱动预算切换、模型推理能力联动、流式增量追加与阶段解析；
- `InlineThinkingBudgetSelector.tsx`: 输入框边角微型思考预算胶囊切换器；
- `InlineReasoningTimelineBox.tsx`: 消息气泡内的毛玻璃内联时间轴与展开折叠收纳盒，带动态脉冲动画与分阶段展开卡片。
