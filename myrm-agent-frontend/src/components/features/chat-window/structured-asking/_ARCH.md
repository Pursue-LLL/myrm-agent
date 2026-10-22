# Structured Asking Card Architecture (`structured-asking`)

## 模块定位
负责全端结构化提问卡片组件、单选/多选/确认/自定义输入多表单形态、键盘数字（`1~9`）与 Tab/Enter 盲打快捷流、以及优雅「跳过由你决定」容错回退机制（Item 47 P0 · 对标 OpenClaw 2026.8.1 结构化提问体验）。

## 文件职责清单

| 文件名 | 类型 | 职责说明 | 状态 |
| :--- | :--- | :--- | :--- |
| `structuredAskingTypes.ts` | 类型 | 领域类型定义：QuestionType, QuestionOption, StructuredQuestionPayload, StructuredQuestionResponse, StructuredQuestionCardProps | ✅ |
| `useStructuredAskingStore.ts` | 状态库 | 管理提问草稿选中项、自由文本输入槽、跳过与作答结果组装状态机 | ✅ |
| `StructuredQuestionCard.tsx` | 决策卡片 | 统一卡片渲染（单选/多选/确认/输入）、推荐项高亮、数字键位提示、一键跳过与提交控制 | ✅ |
| `index.ts` | 门面 | 统一导出所有类型、状态库与卡片组件 | ✅ |
| `_ARCH.md` | 文档 | 模块定位与架构清单 | ✅ |
