# settings/sections/ai-core/ 模块架构

## 架构概述

Settings「AI Core」分组：模型、搜索、Agent 与评估相关 Section。Agent 能力细项见 [agent/_ARCH.md](agent/_ARCH.md)。

## 文件清单

| 文件                        | 职责                                                                                                                                                                                                      |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ModelSettingsSection.tsx`  | 模型 Tab 容器                                                                                                                                                                                             |
| `DefaultModelSection.tsx`   | 默认模型选择；含 visionFallbackModel 双槽、视觉链路 health 探活、text-only 主模型下一键推荐（含 auto health）；主/lite 模型未配置 fallback 时 amber 预警（`noFallbackWarning` / `liteNoFallbackWarning`） |
| `ModelServiceSection.tsx`   | 模型服务与路由                                                                                                                                                                                            |
| `SearchSection.tsx`         | 搜索服务 Settings：manifest 驱动 provider 列表、Priority 1–5、启用冲突提示、单卡 verify                                                                                                                   |
| `AgentsSection.tsx`         | Agent 列表与管理                                                                                                                                                                                          |
| `AgentEditPanel.tsx`        | Agent 编辑侧栏；`#loadout`/`#secrets` hash 自动选中对应 Tab                                                                                                                                               |
| `CloneAgentDialog.tsx`      | 克隆 Agent 对话框                                                                                                                                                                                         |
| `WorkspaceRulesSection.tsx` | 工作区规则                                                                                                                                                                                                |
| `EvaluationSection.tsx`     | 评估与 Instinct Inbox 入口                                                                                                                                                                                |

## 依赖

- [sections/_ARCH.md](../_ARCH.md)
- [agent/_ARCH.md](agent/_ARCH.md)
