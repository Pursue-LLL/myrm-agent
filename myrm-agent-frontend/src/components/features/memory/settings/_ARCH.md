# memory/settings/

## 架构概述

记忆设置区：功能开关、分区 Tab 切换与回收站。

## 文件清单

| 文件                        | 地位 | 职责                                     | I/O/P |
| --------------------------- | ---- | ---------------------------------------- | ----- |
| `MemorySettingsToggles.tsx` | 核心 | 记忆相关功能开关（启用/召回/自动写入等） | ✅    |
| `MemoryTabSwitcher.tsx`     | 核心 | 记忆设置分区 Tab 切换                    | ✅    |
| `MemoryTrashPanel.tsx`      | 核心 | 回收站面板：已删记忆查看与还原           | ✅    |

## 依赖

- `@/store/*`、`@/services/memory`、`@/components/primitives/*`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
