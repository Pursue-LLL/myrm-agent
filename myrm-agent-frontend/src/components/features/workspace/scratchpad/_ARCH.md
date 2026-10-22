# workspace/scratchpad/

## 架构概述

极速临时便签与工作区项目升格调度前端模块。
提供双轨轻量便签抽屉/弹窗、Markdown 编辑/预览、字数统计、localStorage 防丢草稿恢复以及一键向后端 `/api/v1/workspace/promote` 发起升格并将临时想法转化为正式沙箱工程。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `scratchpadTypes.ts` | 类型 | 便签草稿、升格请求与响应契约类型（零 `any`） |
| `useScratchpadStore.ts` | 状态 | Zustand 状态管理，localStorage 自动持久化同步与升格 HTTP 调用 |
| `QuickScratchpadModal.tsx` | 组件 | 原生 `<dialog>` 弹窗，支持全量 Lucide SVG 矢量图标、Markdown 预览、字数统计与一键升格确认 |
| `index.ts` | 门面 | 统一导出便签核心组件、状态库与契约类型 |
| `_ARCH.md` | 架构 | 模块架构设计说明与组件索引 |

## 依赖关系

- 父模块：[`../_ARCH.md`](../_ARCH.md)
- 后端 API：POST `/api/v1/workspace/promote`
- 国际化：`locales/{lang}.json` 的 `scratchpad` 命名空间
