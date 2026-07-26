# theme/

## 架构概述

主题、皮肤、字体等外观偏好的初始化与运行时管理。支持 light/dark/system 三种模式，system 模式通过 `enableSystem` 实时跟随 OS 亮暗偏好切换。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ThemeProvider.tsx` | 核心 | next-themes 封装；初始化 theme-color meta、skin（data-skin）、font（data-font + --font-override）偏好 | ✅ |

## 依赖

- `next-themes` — 亮/暗/system 主题切换（`enableSystem` 启用 OS 跟随）
- `@/lib/fonts` — 字体常量与动态加载
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
