# settings/sections/ai-core/ 模块架构

## 架构概述

Settings「AI Core」分组：模型、搜索、Agent 与评估相关 Section。Agent 能力细项见 [agent/_ARCH.md](agent/_ARCH.md)。

## 文件清单

| 文件                                 | 职责                                                                                                                                                                                                      |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ModelSettingsSection.tsx`           | 模型 Tab 容器                                                                                                                                                                                             |
| `ModelOrchestrationPlaybookCard.tsx` | 模型编排全景手册引导卡片，展示 Brain & Hands、三阶动态路由与 MoA 混合共识最佳实践                                                                                                                         |
| `DefaultModelSection.tsx`            | 默认模型选择；含 visionFallbackModel 双槽、视觉链路 health 探活、text-only 主模型下一键推荐（含 auto health）；主/lite 模型未配置 fallback 时 amber 预警（`noFallbackWarning` / `liteNoFallbackWarning`）；嵌入模型区下方挂载 `MemoryMigrationNotice` |
| `MemoryMigrationNotice.tsx`          | 更换嵌入模型后的记忆迁移提示：存在孤儿记忆时显示迁移入口；迁移中显示 done/total 进度（`role=status` 的 `output`）；结束后按 migrated/skipped/failed 分三种结果——全部完成、已是最新、部分失败（保留提醒并可重试）；请求/轮询出错显示可重试的错误提示。状态由 `useRetrievalStore` 持有，离开设置页后迁移仍在服务端继续 |
| `ModelServiceSection.tsx`            | 模型服务与路由                                                                                                                                                                                            |
| `SearchSection.tsx`                  | 搜索服务 Settings：manifest 驱动 provider 列表、Priority 1–5、启用冲突提示、单卡 verify                                                                                                                   |
| `AgentsSection.tsx`                  | Agent 列表与管理；「导入」打开 Agent Plugins `.zip` 导入对话框（`features/plugins/PluginImportDialog`），完成后刷新列表                                                                                   |
| `AgentEditPanel.tsx`                 | Agent 编辑侧栏；`#loadout`/`#secrets` hash 自动选中对应 Tab；「导出」打开专家导出对话框（`features/plugins/ExpertExportDialog`）；新建页的 AI 构建流程见 `hooks/agent/useAgentAiBuild`                    |
| `CloneAgentDialog.tsx`               | 克隆 Agent 对话框                                                                                                                                                                                         |
| `WorkspaceRulesSection.tsx`          | 工作区规则                                                                                                                                                                                                |
| `EvaluationSection.tsx`              | 评估与 Instinct Inbox 入口                                                                                                                                                                                |

## 依赖

- [sections/_ARCH.md](../_ARCH.md)
- [agent/_ARCH.md](agent/_ARCH.md)
