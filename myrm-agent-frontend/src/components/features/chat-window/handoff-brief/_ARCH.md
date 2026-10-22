# handoff-brief 架构自文档

| 文件 | 类型 | 职责描述 | 状态 |
| :--- | :--- | :--- | :--- |
| `handoffBriefTypes.ts` | 类型契约 | 跨会话交接简报实体、决策/待办条目与上下文注入 Payload 契约 | ✅ 稳定 |
| `useHandoffBriefStore.ts` | 状态机 | 双缓冲预计算简报状态机、人机在环条目开关与标准化注入 Prompt 构造器 | ✅ 稳定 |
| `HandoffDecisionItemRow.tsx` | UI 组件 | 单条决策/待办行内实时编辑、分类徽章与复选框勾选组件 | ✅ 稳定 |
| `HandoffBriefReviewDrawer.tsx` | UI 组件 | 原生语义化 `<dialog>` 可视化审阅抽屉，支持毫秒级秒开、分类筛选、补充决策与一键注入 | ✅ 稳定 |
| `index.ts` | 模块入口 | 统一导出所有契约、Hook 与组件 | ✅ 稳定 |
