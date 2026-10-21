# components/features/artifacts/ui_alignment 模块架构

---

## 架构概述

多轮 UI 设计图视觉对齐与变体决策工作流客户端组件（Item 39 P0）。
支持多套 UI 变体并排比选（Modern Bento, Minimal Dark, Glassmorphism, Neo Brutalism, Custom）、画布交互矩形标注遮罩层（VisualAnnotationOverlay）、以及将用户选定的方案与视觉批注固化为 VisualContract 强约束契约，彻底消除下游编码代理在样式与结构上的歧义。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `uiAlignmentTypes.ts` | 类型 | 领域类型定义：UiVariantItem、VisualAnnotationItem、VisualContractItem、UiAlignmentState |
| `useUiAlignmentStore.ts` | 状态 | Zustand 状态管理：变体与批注拉取、注册、标注添加、契约固化 |
| `VisualAnnotationOverlay.tsx` | 组件 | 画布交互批注层，支持矩形选框绘制、批注保存与 Tooltip 悬浮展示 |
| `UiVariantCompareViewer.tsx` | 组件 | 多变体并排比选卡片、高亮选定方案、一键开启批注与契约固化操作栏 |
| `index.ts` | 门面 | 聚合导出模块内组件与状态 Hook |
| `_ARCH.md` | 文档 | 模块架构描述与文件清单 |

---

## 依赖关系

- `lucide-react`（矢量图标）
- `next-intl`（国际化）
- `zustand`（前端状态管理）
- `/api/v1/chats/{chat_id}/ui-variants` 后端 API 路由
