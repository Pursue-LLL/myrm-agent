# image-editor/ 模块架构

## 架构概述

基于 Canvas API 的轻量级图片标注编辑器。支持在对话中对 AI 生成的图片和截图进行标注（6 种工具：画笔/矩形/椭圆/箭头/文字/马赛克），标注后一键发送回对话供 VLM 分析。零外部依赖，lazy load 零初始成本。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ImageEditor.tsx` | 核心 | 全屏编辑器 overlay：Canvas 画布 + 工具栏 + 颜色/笔触选择 + 发送/取消 | ✅ |
| `useImageEditor.ts` | 核心 | 编辑器状态管理 Hook：工具切换、绘图操作栈、撤销/重做、旋转、导出 | ✅ |
| `uploadAnnotated.ts` | 辅助 | `blobToDataUrl` 工具函数；标注图片上传并插入对话（ToolImageGallery / MediaPreview） | ✅ |
| `tools/` | 辅助 | Canvas 绘图原语（类型 + 渲染引擎） | [tools/_ARCH.md](tools/_ARCH.md) |

## 集成点

- `message-box/ToolImageGallery.tsx` — Lightbox 顶部 toolbar 的"标注"按钮
- `message-input-actions/AttachList.tsx` — 附件缩略图 hover「编辑」按钮
- `artifacts/renderers/MediaPreview.tsx` — ImagePreview 悬浮"标注"按钮

## 依赖

- `@/services/file` — 标注后的图片上传
- `@/store/useChatStore` — 上传后附件插入对话
- `lucide-react` — 工具图标
- `next-intl` — 国际化
