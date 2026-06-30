# canvas/ 模块架构

## 架构概述

Infinite canvas workspace UI module based on tldraw.

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CanvasWorkspace.tsx` | 核心 | tldraw 编辑器封装：snapshot 持久化、selection 同步、SSE 实时更新（含自动重连） | ✅ |
| `CanvasListPage.tsx` | 核心 | 画布列表：创建、重命名、删除（AlertDialog 确认）、跳转编辑、i18n | ✅ |

## 依赖

- `tldraw` — infinite canvas 渲染引擎
- `next-intl` — 国际化（useTranslations）
- `@/services/canvas` — Canvas REST API service
- `@/store/useCanvasStore` — Canvas Zustand store
- `@/components/primitives/alert-dialog` — shadcn AlertDialog
- `lucide-react` — 图标库
