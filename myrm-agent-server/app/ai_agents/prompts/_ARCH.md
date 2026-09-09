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
| `deliverable_discipline.py` | ✅ 辅助 | Deliverable-first SSOT（Knowledge Work / builtin-economy user_instructions；含 kanban 任务板引导 + 反幻觉写文件约束；不绑定具体工具名，工具由 schema 暴露） |

---

## Prompt Mode 四档设计

| Mode | Token 量 | 注入内容 | 适用场景 |
|------|----------|----------|----------|
| `full` | ~2500 chars | 身份+绝对服从+回复规则+任务完整性（安全边界由 SecurityBoundaryMiddleware 在 messages[1] 统一注入） | 通用场景（默认） |
| `lean` | ~1200 chars | 身份+任务完整性（安全边界由 SecurityBoundaryMiddleware 统一注入） | WEAK/MEDIUM 模型自动适配；高级用户减少干扰 |
| `naked` | ~300 chars | 工具调用指引（安全边界由 SecurityBoundaryMiddleware 在 messages[1] 统一注入） | 完全用户控制与轻量测试 |
| `search` | ~1200 chars | 搜索专用提示词（来自 fast_search_agent_prompt.py，安全边界由 SecurityBoundaryMiddleware 统一注入）| 快速搜索模式 |

search 模式通过 `_SEARCH_PROMPT_BASE`（normal）+ `SEARCH_DEEP_SUFFIX`（deep）静态缓存，
保证 Kv Cache 前缀稳定性。deep suffix 在 factory.py 中按 `search_depth` 动态追加。

通用防御规则（XML 工具调用防御、上下文优先检查、工具使用纪律等）由框架层
`model_discipline.py` 的 `AGENT_CORE_RULES` 提供，业务层仅包含
身份定义和 `request_answer_user_tool` 自审规则。

工具规则解耦（Self-contained Tooling）：
- 记忆工具（`memory_save_tool` 等）的使用规则内聚于工具自身的 Description 中，System Prompt 保持纯净，不耦合记忆规则，杜绝状态组合膨胀与幽灵工具调用。
- `enable_answer_tool`：控制 identity 和 ruleset 中 answer_tool 引导的注入（4 组静态单例 Map：is_zh × enable_answer_tool）。

架构决策记录（ADR）：对话人格双语 vs 工具契约统一英文单例
- **双语对话人格**：业务层 System Prompt（`CORE_SYSTEM_PROMPT_*`）支持中英双语，保证大模型面向用户的回复语气、风格与语言习惯自然贴合用户设定。
- **底层工具调用协议全局统一英文**：桌面控制（`DESKTOP_CONTROL_RULES`）等底层操作系统级调用指引，在 `factory.py` 中强制采用静态英文单例。
  1. **对齐大模型 Function Calling 训练先验**：大模型的工具调用 RLHF 数据集绝大多数基于英文代码与 API 语境，英文提示词能零翻译损耗直接映射参数（如 `ref`, `action`, `wait_seconds`），杜绝跨语言 Attention 折损引发的参数幻觉。
  2. **绝对最大化 KV Cache 前缀复用**：桌面规则作为全局不可变静态常量追加，保证不同语言用户在同一沙箱/桌面服务中的前缀缓存 100% 字节级恒定复用，防止动态分叉导致前缀命中率雪崩。

中间件条件逻辑：
- `citation_rules_middleware`：naked/search 模式跳过（lean/full 在有外部来源时注入）
- `widget_capability_middleware`：naked 模式跳过
