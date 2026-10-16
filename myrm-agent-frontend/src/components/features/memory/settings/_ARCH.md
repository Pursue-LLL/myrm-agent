# memory/settings/

## 架构概述

记忆设置区：功能开关、分区 Tab 切换、回收站与更换嵌入模型后的记忆迁移提示。

## 文件清单

| 文件                        | 地位 | 职责                                     | I/O/P |
| --------------------------- | ---- | ---------------------------------------- | ----- |
| `MemorySettingsToggles.tsx` | 核心 | 记忆相关功能开关（启用/召回/自动写入等） | ✅    |
| `MemoryTabSwitcher.tsx`     | 核心 | 记忆设置分区 Tab 切换                    | ✅    |
| `MemoryTrashPanel.tsx`      | 核心 | 回收站面板：已删记忆查看与还原           | ✅    |
| `MemoryMigrationNotice.tsx` | 核心 | 更换嵌入模型后的记忆迁移提示：挂载时读取遗留记忆数，说明其迁移前不参与回复并给出迁移入口；迁移中显示 done/total 进度（`output` 状态区）；结束后分全部完成、已是最新、部分失败（保留提醒并可重试）三种结果，请求或轮询出错给出可重试提示。由 `Models → Embedding` 与 `Memory` 两处挂载，迁移状态由 `useRetrievalStore` 持有，离开设置页后迁移仍在服务端继续 | ✅    |

## 依赖

- `@/store/*`、`@/services/memory`、`@/components/primitives/*`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
