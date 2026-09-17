# theme-studio/preview/

## 架构概述

Theme Studio 的编译器驱动预览：把草案 `ThemeProfileRecipe` 编译为 Myrm 外壳预览，覆盖布局与可读性场景。

## 文件清单

| 文件                     | 地位 | 职责                                         | I/O/P |
| ------------------------ | ---- | -------------------------------------------- | ----- |
| `ThemeStudioPreview.tsx` | 核心 | 编译器驱动外壳预览（布局 + 可读性场景）       | ✅    |

## 依赖

- `@/theme-engine`（POS: 主题编译）
- 父模块 [`../_ARCH.md`](../_ARCH.md)
