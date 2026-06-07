# file-preview 模块架构

## 架构概述

聊天附件图片预览。自动适配 Tauri 本地路径与 Sandbox 已上传 URL，非图片文件不渲染。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `index.ts` | 入口 | 导出 `ImagePreview` 等公共组件 | ✅ |
| `ImagePreview.tsx` | 核心 | 图片懒加载预览（png/jpg/jpeg/gif/webp） | ✅ |

## 使用

```tsx
import { ImagePreview } from '@/components/features/file-preview';
```

## 依赖

- `@/store/chat/types` — `File` 类型（local_path / uploaded）
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
