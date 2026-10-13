# settings/sections/ai-tools/ 模块架构

## 架构概述

Settings「AI Tools」分组：MCP、技能与工具质量仪表盘 Section。

## 文件清单

| 文件                                 | 职责                                                                                        |
| ------------------------------------ | ------------------------------------------------------------------------------------------- |
| `MCPSection.tsx`                     | MCP 服务器配置                                                                              |
| `SkillsSection.tsx`                  | 技能列表与管理；Installed 挂载 `SkillsLearnPanel` + DraftReview；可选 `initialSearch` 直接打开 Installed 并预填搜索 |
| `UnifiedSkillsSection.tsx`           | 统一技能视图容器（inventory / compounding / workflowTemplates / pending / rejections）；把 URL `?search=` 交给 inventory 作为初始搜索（成长看板「管理」链接的落点） |
| `CompoundingChecklistSection.tsx`    | MSC 复利四行 checklist + SkillsLearnPanel 入口                                              |
| `WorkflowTemplateScriptPreview.tsx`  | 库页只读脚本预览（GET detail）                                                              |
| `WorkflowTemplateArgsDialog.tsx`     | Run 前 `{placeholder}` 参数表单（Library Run + Cron 创建复用）                              |
| `WorkflowTemplateLibrarySection.tsx` | DW 命名模板库列表、Run、Export/Import（`lib/workflow/useWorkflowTemplateTransfer`）、Delete |
| `ToolStabilitySection.tsx`           | 工具稳定性统计                                                                              |
| `ToolQualitySection.tsx`             | 工具质量概览                                                                                |
| `SkillQualitySection.tsx`            | 技能质量详情                                                                                |
| `GlobalSkillQualityDashboard.tsx`    | 全局技能质量仪表盘                                                                          |
| `SkillQualityTrendChart.tsx`         | 质量趋势图                                                                                  |
| `QualityDistributionChart.tsx`       | 质量分布图                                                                                  |

## 依赖

- [sections/_ARCH.md](../_ARCH.md)
- `@/services/*` — MCP / 技能 API
