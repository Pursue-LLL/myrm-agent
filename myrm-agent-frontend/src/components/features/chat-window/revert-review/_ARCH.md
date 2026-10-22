# revert-review 架构自文档

| 文件 | 类型 | 职责描述 | 状态 |
| :--- | :--- | :--- | :--- |
| `revertReviewTypes.ts` | 类型契约 | 定义单轮文件变更实体、回滚状态机、行内批注与定向修复 Prompt Payload | ✅ 稳定 |
| `useTurnRevertReviewStore.ts` | 状态机 | Turn 级文件撤销状态机、持久化接口桥接与行内审查批注集中池 | ✅ 稳定 |
| `TurnRevertCard.tsx` | UI 组件 | 会话流消息底部轻量文件变更摘要栏与一键原子回滚确认模态卡片 | ✅ 稳定 |
| `InlineReviewCommentBubble.tsx` | UI 组件 | Diff 视图行内划词/行号浮动批注气泡，支持预设建议与一键定向修复 Prompt 构造 | ✅ 稳定 |
| `DiffReviewContainer.tsx` | 容器组件 | 增强型 Diff 审查容器，无缝扩展 DiffViewer，注入行号交互触发器与批注锚点 | ✅ 稳定 |
| `index.ts` | 模块入口 | 统一导出所有类型、Hook 与 UI 组件 | ✅ 稳定 |
