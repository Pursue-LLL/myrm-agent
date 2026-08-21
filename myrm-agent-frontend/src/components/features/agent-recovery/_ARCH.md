# agent-recovery/

## 架构概述

Agent Profile 启动与配置自愈恢复弹窗组件，提供组件健康状态可视化、隔离项告警、最后已知良好配置（LKG）一键回滚与排障诊断包导出。

## 文件清单

| 文件 | 地位 | 职责 |
| --- | --- | --- |
| `StartupRecoveryDialog.tsx` | 核心组件 | 启动自愈弹窗：展示探针检测结果、隔离项列表、诊断导出与快照回滚 |

## 依赖

- `@/services/agentRecovery` — Profile 恢复与健康探测 API
- `@/components/ui/alert-dialog` — 对话框基础组件
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
