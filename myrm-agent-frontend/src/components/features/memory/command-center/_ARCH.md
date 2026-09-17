# memory/command-center/

## 架构概述

记忆命令中心：诊断、修复与高级编排的统一入口。门面负责面板编排，子面板按职责拆分，避免单文件承载全部诊断逻辑。

## 文件清单

| 文件                                  | 地位 | 职责                                                                 | I/O/P |
| ------------------------------------- | ---- | -------------------------------------------------------------------- | ----- |
| `MemoryCommandCenter.tsx`             | 门面 | 命令中心主布局：数据装配、面板编排与跨面板状态协调                   | ✅    |
| `MemoryCommandCenterPanels.tsx`       | 核心 | 主内容区面板集合（概览/召回/健康等基础面板）                         | ✅    |
| `MemoryCommandCenterAdvancedPanels.tsx` | 核心 | 高级面板集合（容量剧场、偏好雷达、检索诊断等进阶视图）             | ✅    |
| `MemoryCommandCenterDoctorPanel.tsx`  | 核心 | 记忆医生面板：诊断项、自动修复动作与修复结果趋势                     | ✅    |
| `MemoryCommandCenterChrome.tsx`       | 辅助 | 命令中心外壳（标题、工具栏、tab 切换与操作区）                       | ✅    |
| `MemoryRecallBoundaryPanel.tsx`       | 辅助 | 召回边界面板：注入预算与截断披露                                     | ✅    |
| `CognitiveClockPanel.tsx`             | 核心 | 多频认知时钟状态面板：T0-T3 状态指示、前台打字让步指示与手动提炼     | ✅    |

## 依赖

- `@/services/memory`、`@/store/*`、`@/components/primitives/*`
- 兄弟子目录 `../cards/`、`../dialogs/`、`../hooks/`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
