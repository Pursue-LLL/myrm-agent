# settings/sections/ai-tools/ 模块架构

## 架构概述

Settings「AI Tools」分组：MCP、技能与工具质量仪表盘 Section。

## 文件清单

| 文件 | 职责 |
|------|------|
| `MCPSection.tsx` | MCP 服务器配置 |
| `SkillsSection.tsx` | 技能列表与管理 |
| `UnifiedSkillsSection.tsx` | 统一技能视图容器 |
| `ToolStabilitySection.tsx` | 工具稳定性统计 |
| `ToolQualitySection.tsx` | 工具质量概览 |
| `SkillQualitySection.tsx` | 技能质量详情 |
| `GlobalSkillQualityDashboard.tsx` | 全局技能质量仪表盘 |
| `SkillQualityTrendChart.tsx` | 质量趋势图 |
| `QualityDistributionChart.tsx` | 质量分布图 |
| `SkillFunnelChart.tsx` | 技能漏斗图 |

## 依赖

- [sections/_ARCH.md](../_ARCH.md)
- `@/services/*` — MCP / 技能 API
