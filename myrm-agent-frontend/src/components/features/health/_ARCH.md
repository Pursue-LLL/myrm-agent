# health/

## 架构概述

System Doctor 健康检查仪表盘与修复引导，含诊断导出能力。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `DoctorDashboard.tsx` | 核心组件 | 系统诊断看板：健康评分、状态过滤、趋势图、修复卡片、诊断导出 |
| `GuidedRepairCard.tsx` | 子组件 | 引导式修复卡片，支持 dry_run 和 confirm |
| `HealthTrendChart.tsx` | 子组件 | 健康趋势折线图 |
| `doctor-icons.tsx` | 图标集 | DoctorDashboard 专用 SVG 图标组件集 |

## 依赖

- `@/services/runtime-health` — /doctor API 客户端
- `@/lib/utils/diagnostic-export` — 诊断报告格式化与导出（Markdown/JSON）
- `@/components/primitives/*` — UI 基础组件
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
