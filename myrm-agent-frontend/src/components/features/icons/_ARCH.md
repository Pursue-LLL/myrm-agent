# icons/

## 架构概述

功能域专用图标组件（非 Lucide 通用集）。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `PremiumIcons.tsx` | facade re-export |
| `premium-icons/core.tsx` | 通用 UI 图标（第 1 批） |
| `premium-icons/extended.tsx` | 通用 UI 图标（第 2 批） |
| `premium-icons/settings.tsx` | 设置页替换 Lucide 图标（第 3 批） |
| `premium-icons/types.ts` | `IconProps` 类型 |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
