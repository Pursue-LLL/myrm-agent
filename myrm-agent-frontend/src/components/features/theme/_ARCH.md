# theme/

## 架构概述

主题、皮肤、字体等外观偏好的初始化与运行时管理。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ThemeProvider.tsx` | 核心 | next-themes 封装；初始化 theme-color meta、skin（data-skin）、font（data-font + --font-override）偏好 | ✅ |

## 依赖

- `next-themes` — 亮/暗主题切换
- `@/lib/fonts` — 字体常量与动态加载
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
