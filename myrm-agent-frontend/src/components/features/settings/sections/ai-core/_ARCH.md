# settings/sections/ai-core/ 模块架构

## 架构概述

Settings「AI Core」分组：模型、搜索、Agent 与评估相关 Section。Agent 能力细项见 [agent/_ARCH.md](agent/_ARCH.md)。

## 文件清单

| 文件                                 | 职责                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ModelSettingsSection.tsx`           | 模型 Tab 容器                                                                                                                                                                                                                                                                                                                                             |
| `ModelOrchestrationPlaybookCard.tsx` | 模型编排全景手册引导卡片，展示 Brain & Hands、三阶动态路由与 MoA 混合共识最佳实践                                                                                                                                                                                                                                                                         |
| `DefaultModelSection.tsx`            | 默认模型页的编排根：provider 初始化/错误态、模型选择环境（`ModelSelectEnvProvider`）、一次性清除失效选择；模型卡（主/快速/后台自进化/智能路由，含视觉与视频备用的 health 探活与一键推荐）见 [default-model/_ARCH.md](../../default-model/_ARCH.md)；模型卡之后挂载检索增强卡 [retrieval/_ARCH.md](../../retrieval/_ARCH.md)（嵌入模型迁移提示由该卡承载） |
| `ModelServiceSection.tsx`            | 模型服务与路由                                                                                                                                                                                                                                                                                                                                            |
| `SearchSection.tsx`                  | 搜索服务 Settings：manifest 驱动 provider 列表、Priority 1–5、启用冲突提示、单卡 verify                                                                                                                                                                                                                                                                   |
| `AgentsSection.tsx`                  | Agent 列表与管理；「导入」打开 Agent Plugins `.zip` 导入对话框（`features/plugins/PluginImportDialog`），完成后刷新列表                                                                                                                                                                                                                                   |
| `AgentEditPanel.tsx`                 | Agent 编辑侧栏；`#loadout`/`#secrets` hash 自动选中对应 Tab；「导出」打开专家导出对话框（`features/plugins/ExpertExportDialog`）；新建页的 AI 构建流程见 `hooks/agent/useAgentAiBuild`                                                                                                                                                                    |
| `CloneAgentDialog.tsx`               | 克隆 Agent 对话框                                                                                                                                                                                                                                                                                                                                         |
| `WorkspaceRulesSection.tsx`          | 工作区规则                                                                                                                                                                                                                                                                                                                                                |
| `EvaluationSection.tsx`              | 评估与 Instinct Inbox 入口                                                                                                                                                                                                                                                                                                                                |

## 依赖

- [sections/_ARCH.md](../_ARCH.md)
- [agent/_ARCH.md](agent/_ARCH.md)
