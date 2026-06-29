# settings/sections/ai-core/ 模块架构

## 架构概述

Settings「AI Core」分组：模型、搜索、Agent 与评估相关 Section。Agent 能力细项见 [agent/_ARCH.md](agent/_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `ModelSettingsSection.tsx` | 模型 Tab 容器 |
| `DefaultModelSection.tsx` | 默认模型选择 |
| `ModelServiceSection.tsx` | 模型服务与路由 |
| `SearchSection.tsx` | 检索与 SearXNG |
| `AgentsSection.tsx` | Agent 列表与管理 |
| `AgentEditPanel.tsx` | Agent 编辑侧栏 |
| `CloneAgentDialog.tsx` | 克隆 Agent 对话框 |
| `WorkspaceRulesSection.tsx` | 工作区规则 |
| `EvaluationSection.tsx` | 评估与 Instinct Inbox 入口 |

## 依赖

- [sections/_ARCH.md](../_ARCH.md)
- [agent/_ARCH.md](agent/_ARCH.md)
