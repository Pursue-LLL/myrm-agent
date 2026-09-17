# memory/cards/

## 架构概述

单条记忆的展示件：卡片、类型图标、统计、详情 Sheet、冲突卡与证据徽标。纯展示层，数据与动作由父级 `memory/` 容器注入。

## 文件清单

| 文件                             | 地位 | 职责                                                             | I/O/P |
| -------------------------------- | ---- | ---------------------------------------------------------------- | ----- |
| `MemoryCard.tsx`                 | 核心 | 单条记忆卡：内容、类型、状态、权重与操作入口                     | ✅    |
| `MemoryTypeIcon.tsx`             | 核心 | 记忆类型图标映射（语义/情景/程序/任务摘要等）                    | ✅    |
| `MemoryStats.tsx`                | 核心 | 记忆库统计概览（总量、类型分布、活跃/归档）                      | ✅    |
| `MemoryDetailSheet.tsx`          | 核心 | 记忆详情 Sheet：正文、元数据、演变历史时间线与纠正链             | ✅    |
| `ConflictCard.tsx`               | 核心 | 冲突记忆并排对比与处置入口                                       | ✅    |
| `ConflictResolutionCard.tsx`     | 核心 | 命令中心冲突解决卡：合并/保留/丢弃决策                           | ✅    |
| `EvidenceBadge.tsx`              | 辅助 | 证据溯源徽标（来源会话/工件标记）                                | ✅    |
| `RepoEvidenceCard.tsx`           | 辅助 | 仓库历史证据卡片（提交/文件级来源）                              | ✅    |
| `MemoryScopeHierarchyCard.tsx`   | 辅助 | 记忆作用域层级卡（全局/工作区/会话）                             | ✅    |
| `MemoryScopePicker.tsx`          | 辅助 | 作用域选择器                                                     | ✅    |
| `PreferenceStabilityCard.tsx`    | 辅助 | 偏好稳定性卡（动态信号权重收敛度）                               | ✅    |
| `TasteSummaryCard.tsx`           | 辅助 | 偏好雷达摘要卡                                                   | ✅    |

## 依赖

- `@/store/*`、`@/components/primitives/*`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
