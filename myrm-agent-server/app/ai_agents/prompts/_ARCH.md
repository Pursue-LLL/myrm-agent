# ai_agents/prompts 模块架构


---

## 架构概述

共享提示词模块。为各类 Agent 提供可复用的系统提示词和规则。
支持两档 Prompt Mode（full/search），由系统决定：内置快速 / 深度搜索智能体用 search，其余智能体（含自定义）用 full；模型名与上下文窗口不改变提示词。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `general_agent_prompt.py` | ✅ 核心 | 通用 Agent 系统提示词（两档预构建 + get_core_system_prompt API；`coerce_prompt_mode` 把库里存的自由字符串收窄为已知档位，search 以外一律按 full） |
| `fast_search_agent_prompt.py` | ✅ 核心 | 搜索模式提示词（被 general_agent_prompt search 模式静态引用；回复规则取 `SEARCH_RESPONSE_RULES_*`） |
| `shared_rules.py` | ✅ 辅助 | 跨 Agent 共享规则常量；回复规则分两套：`AGENT_RESPONSE_RULES_*` 供 full 档（篇幅随问题复杂度，Markdown 与表格以渠道 `[Output Format]` 声明为准），`SEARCH_RESPONSE_RULES_*` 供 search 档与快速搜索（全面详细的综合答案），公式契约 `_LATEX_RULES_*` 两套共用；语言一致性条款默认跟随用户提问的语言，用户当前消息或已存记忆指定了回复语言时以指定为准 |
| `deliverable_discipline.py` | ✅ 辅助 | Deliverable-first SSOT（Knowledge Work / builtin-economy user_instructions；含 kanban 任务板引导 + 反幻觉写文件约束；不绑定具体工具名，工具由 schema 暴露） |

---

## Prompt Mode 两档设计

| Mode | Token 量（`o200k_base`，英 / 中，不含 answer 工具引导；开启后约各 +76 / +82） | 注入内容 | 适用场景 |
|------|----------|----------|----------|
| `full` | 613 / 798 | 身份+回复规则（Agent 版）+任务完整性（安全边界由 SecurityBoundaryMiddleware 统一注入） | 通用场景（默认） |
| `search` | 1,135 / 1,844 | 搜索专用提示词（来自 fast_search_agent_prompt.py，含搜索版回复规则，安全边界由 SecurityBoundaryMiddleware 统一注入）| 快速搜索模式 |

体积门禁：full 档与 harness 拼在它后面的静态块（时间规则、核心行为规则、渠道输出提示）合计，由 `tests/architecture/test_first_turn_static_prompt_budget.py` 按语言封顶；往里加字的改动须在同一 PR 抬高上限并说明理由。

search 模式通过 `_SEARCH_PROMPT_BASE`（normal）+ `SEARCH_DEEP_SUFFIX`（deep）静态缓存，
保证 Kv Cache 前缀稳定性。deep suffix 在 `general_agent/factory/prompt.py` 中按 `search_depth` 动态追加。

通用防御规则（XML 工具调用防御、上下文优先检查、工具使用纪律等）由框架层
`agent_core_rules.py` 的 `AGENT_CORE_RULES` 提供，业务层仅包含
身份定义和 `request_answer_user_tool` 自审规则。

工具规则解耦（Self-contained Tooling）：
- 记忆工具（`memory_save_tool` 等）的使用规则内聚于工具自身的 Description 中，System Prompt 保持纯净，不耦合记忆规则，杜绝状态组合膨胀与幽灵工具调用。
- `enable_answer_tool`：控制 identity 和 ruleset 中 answer_tool 引导的注入（4 组静态单例 Map：is_zh × enable_answer_tool）。

架构决策记录（ADR）：对话人格双语 vs 工具契约统一英文单例
- **双语对话人格**：业务层 System Prompt（`CORE_SYSTEM_PROMPT_*`）支持中英双语，保证大模型面向用户的回复语气、风格与语言习惯自然贴合用户设定。
- **底层工具调用协议全局统一英文**：桌面控制（`DESKTOP_CONTROL_RULES`）等底层操作系统级调用指引只有英文版，由 `general_agent/factory/prompt.py` 在挂载桌面控制工具时（`mount_computer_use`）追加为静态常量。
  1. **对齐大模型 Function Calling 训练先验**：大模型的工具调用 RLHF 数据集绝大多数基于英文代码与 API 语境，英文提示词能零翻译损耗直接映射参数（如 `ref`, `action`, `wait_seconds`），杜绝跨语言 Attention 折损引发的参数幻觉。
  2. **最大化 KV Cache 前缀复用**：桌面规则作为全局不可变静态常量追加，保证不同语言用户在同一沙箱/桌面服务中的该段前缀字节一致，避免动态分叉导致前缀命中率下降。

中间件条件逻辑：
- `citation_rules_middleware`：search 模式跳过（full 在有外部来源时注入）
- `widget_capability_middleware`：只在 web_chat 渠道的 full 模式挂载（`mount_resolver.mount_widget_capability`）；搜索面以及 IM、定时、语音、看板、评测不挂
