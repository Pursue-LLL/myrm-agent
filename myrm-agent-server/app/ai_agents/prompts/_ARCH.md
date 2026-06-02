# ai_agents/prompts 模块架构


---

## 架构概述

共享提示词模块。为各类 Agent 提供可复用的系统提示词和规则。
支持四档 Prompt Mode（full/lean/naked/search），per-agent 可配置。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `general_agent_prompt.py` | ✅ 核心 | 通用 Agent 系统提示词（四档预构建 + get_core_system_prompt API） |
| `fast_search_agent_prompt.py` | ✅ 核心 | 搜索模式提示词（被 general_agent_prompt search 模式静态引用） |
| `search_suggestions.py` | ✅ 辅助 | 搜索建议生成提示词 |
| `shared_rules.py` | ✅ 辅助 | 跨 Agent 共享规则常量 |

---

## Prompt Mode 四档设计

| Mode | Token 量 | 注入内容 | 适用场景 |
|------|----------|----------|----------|
| `full` | ~3600 chars | 身份+精简规则+绝对服从+回复规则+安全+任务完整性+记忆（条件） | 通用场景（默认） |
| `lean` | ~2200 chars | 身份+精简规则+安全+任务完整性 | 高级用户减少干扰 |
| `naked` | ~655 chars | 安全规则+工具调用指引 | 完全用户控制 |
| `search` | ~1200 chars | 搜索专用提示词（来自 fast_search_agent_prompt.py）| 快速搜索模式 |

search 模式通过 `_SEARCH_PROMPT_BASE`（normal）+ `SEARCH_DEEP_SUFFIX`（deep）静态缓存，
保证 Kv Cache 前缀稳定性。deep suffix 在 factory.py 中按 `search_depth` 动态追加。

通用防御规则（XML 工具调用防御、上下文优先检查、工具使用纪律等）由框架层
`model_discipline.py` 的 `AGENT_CORE_RULES` 提供，业务层仅包含
身份定义和 `request_answer_user_tool` 自审规则。

工具感知条件注入：
- `MEMORY_RULES`：仅当 `enable_memory=True` 时注入 full 模式（避免引用不存在的工具）
- `enable_answer_tool`：控制 identity 和 ruleset 中 answer_tool 引导的注入

中间件条件逻辑：
- `citation_rules_middleware`：naked/lean/search 模式跳过
- `widget_capability_middleware`：naked 模式跳过
