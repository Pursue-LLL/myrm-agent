# components/features/system-monitor/

## 架构概述

本地与沙箱系统级可观测性监控层，聚焦端口占用一键排查、父子进程树溯源（Launch Lineage）以及高耗与僵尸进程安全查杀。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.ts` | 类型 | 端口占用进程与父子派生链 TypeScript 契约定义 | ✅ |
| `ProcessLineageView.tsx` | 组件 | 进程启动父子调用树面包屑与高耗进程橙色预警视图 | ✅ |
| `PortConflictModal.tsx` | 组件 | 端口冲突检测弹窗、占用详情透视与一键安全查杀交互视窗 | ✅ |
| `index.ts` | 门面 | 聚合导出模块内所有组件与类型定义 | ✅ |
