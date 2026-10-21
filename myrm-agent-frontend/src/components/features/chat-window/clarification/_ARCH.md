# 苏格拉底式模糊需求反向澄清门禁与规格提炼器架构清单

| 文件 | 类型 | 职责描述 | 状态 |
| :--- | :--- | :--- | :--- |
| `clarificationGateTypes.ts` | 契约定义 | 澄清问题、选项胶囊、用户决策归属与无歧义 GoalSpec 核心类型契约 | 稳定生效 |
| `useClarificationGateStore.ts` | 状态机 | 需求模糊度自检、/grill-me 指令捕获、选项收集、跳过默认假设与 GoalSpec 编译器 | 稳定生效 |
| `ClarificationPromptBar.tsx` | UI组件 | 会话输入框上方浮条，智能提示简略需求风险并提供一键理清思路与跳过触发器 | 稳定生效 |
| `ClarificationGateDrawer.tsx` | UI组件 | 原生语义化澄清抽屉，展示结构化选项胶囊、补充文本框、一键跳过与确认提炼 | 稳定生效 |
| `index.ts` | 统一出口 | 聚合导出需求反向澄清门禁所有类型契约、状态机 Hook 与视图组件 | 稳定生效 |
