# question-nav/

## 架构概述

长会话用户提问智能视口穿梭导航器与多轮 Prompt 索引大纲抽屉（Item 43 P0）。
解决数十轮长任务中翻找当初发问指令费时费力、反复滚动滑过头的交互痛点。
提供：
1. 视口右侧 `⏫`/`⏬` 智能上一问/下一问居中平滑跳转悬浮胶囊；
2. 悬停上一跳/下一跳用户问题的截断极速摘要 Tooltip；
3. 全会话 User Prompt 结构化大纲索引抽屉（`<dialog open>` 语义，支持直达指定轮次）；
4. 与现有 `ScrollToBottomButton` 待读条数精确计数和微行渐进披露协同。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|---|---|---|---|
| `userQuestionNavTypes.ts` | 类型 | 领域类型定义：UserQuestionAnchor, PendingCountCueItem, QuestionNavState | ✅ |
| `useUserQuestionNavStore.ts` | 状态 | Zustand 状态管理：解析提取 User 消息提问索引、当前视口游标、抽屉开闭、下方待读条目 | ✅ |
| `UserQuestionNav.tsx` | 组件 | 视口右侧悬浮胶囊工具栏：⏫ 上一问、题号指示器、⏬ 下一问，带悬停提问摘要 Tooltip | ✅ |
| `UserQuestionOutlineDrawer.tsx` | 组件 | 多轮提问大纲抽屉模态浮层：列表化呈现全会话提问序号与摘要，支持直达指定轮次 | ✅ |
| `index.ts` | 门面 | 统一对外导出公共组件、Hook 与领域类型 | ✅ |
