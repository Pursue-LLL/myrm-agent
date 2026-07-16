# premium-icons/ 模块架构

## 架构概述

`PremiumIcons.tsx` 的 SVG 图标实现分片。按添加批次分为三文件，每文件 ≤400 行；`PremiumIcons.tsx` 仅 re-export。

## 文件清单

| 文件 | 职责 |
|------|------|
| `types.ts` | `IconProps` 共享类型 |
| `core.tsx` | 通用 UI 图标（第 1 批，33 个） |
| `extended.tsx` | 通用 UI 图标（第 2 批，33 个） |
| `settings.tsx` | 设置页 Lucide 替换图标（第 3 批，33 个） |

## 依赖

- 父模块 [icons/_ARCH.md](../_ARCH.md)
