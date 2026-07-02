# image-editor/tools/ 模块架构

## 架构概述

图片标注编辑器的 Canvas 绘图原语：工具类型常量与纯函数渲染引擎。无 React 依赖，由 `useImageEditor.ts` 调用。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.ts` | 核心 | `ToolType`、调色板/线宽/限制常量 | ✅ |
| `drawingEngine.ts` | 核心 | rect/ellipse/arrow/freehand/text/blur 的 Canvas 2D 渲染 | ✅ |

## 依赖

- 父模块 [`../_ARCH.md`](../_ARCH.md)
