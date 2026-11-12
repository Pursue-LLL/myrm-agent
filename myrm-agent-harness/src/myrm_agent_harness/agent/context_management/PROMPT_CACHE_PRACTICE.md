# Prompt Cache 实践：框架的真实应用与实现

>
> | 章节 | 关联源代码 |
> |------|-----------|
> | §2.1 工具分层排序 | `tool_management/tool_layers.py`, `tool_management/registry.py` |
> | §2.2 时间戳注入 & Agent 行为规则 | `streaming/utils.py`, `base_agent.py` |
> | §2.3 Cron 场景 | `app/core/cron/adapters/agent_runner/` |
> | §2.4 安全边界与用户指令注入 | `app/ai_agents/agent_middlewares/user_instructions_middleware.py` |
> | §2.5–2.6 记忆 / 入账 Human 前缀 | `agent/middlewares/memory_context/memory_context_middleware.py`；`app/core/utils/delivery_provenance.py`、`app/core/channel_bridge/agent_executor/helpers.py`、`app/ai_agents/general_agent/stream_pipeline.py`、`myrm-agent-server/app/api/agents/general_agent/streaming.py`、`app/services/agent/wakeup_handler.py` |
> | §2.6.3 运行内视图稳定与签名推理块回放 | `agent/middlewares/_run_notices.py`, `core/message_tail.py`, `core/thinking_blocks.py`, `agent/middlewares/thinking_replay_guard_middleware.py`, `toolkits/llms/transport/anthropic_messages.py`, `toolkits/llms/transport/anthropic_thinking.py`, `pipeline/processors/thinking_cleaner.py`, `pipeline/processors/media_filter.py`, `pipeline/processors/active_tool_result_prune_processor.py`, `pipeline/processors/cache_ttl_prune_processor.py`, `pipeline/processors/compress_processor.py`, `pipeline/processors/summarize_processor/processor.py`, `infra/cache_policy.py` |
> | §3 显式缓存优化器 | `pipeline/processors/cache_optimizer.py` |
> | §4.1 压缩的触发与让位 | `pipeline/processors/compress_processor.py`, `pipeline/processors/summarize_processor/processor.py` |
> | §4.2 compress_min_save | `infra/schemas/` |
> | §4.3 动态阈值 | `infra/context_budget.py` |
> | §4.4 可逆压缩 | `strategies/compactor/compactor.py` |
> | §4.5 摘要与缓存生命周期 | `strategies/summary/summarizer/` |
> | §5.1.1 Cache-TTL 归档恢复闭环 | `pipeline/processors/cache_ttl_prune_processor.py`, `pipeline/processors/cache_ttl_prune_archive.py`, `pipeline/processors/cache_ttl_prune_roi.py`, `infra/archive_reference.py`, `tracking/task_metrics.py`, `meta_tools/file_ops/core/file_operation_service.py` |
> | §5 Pipeline | `pipeline/engine.py`, `middlewares/context_pipeline/context_pipeline_middleware.py` |
> | §6.1-6.2 LLM 层 | `toolkits/llms/core/llm.py` |
> | §6.3 缓存可观测性 | `utils/token_economics/tracker.py`, `toolkits/llms/utils/logger.py` |
> | §6.3 层次5 缓存断裂诊断 | `infra/cache_break_detector.py`, `infra/cache_metrics_collector.py` |
> | §6.4 前缀缓存预热与空闲保活 | `preheat.py`, `base_agent.py` |

本文档记录 myrm-agent-harness 框架对 Prompt Cache 的真实实践和应用。
与 [CONTEXT_ENGINEERING.md](./CONTEXT_ENGINEERING.md) 的业界理论对照，本文聚焦于**框架代码中的具体实现**。

---

## 目录

1. [整体策略](#1-整体策略)
2. [前缀稳定性保障](#2-前缀稳定性保障) — 工具分层排序、时间戳注入、用户指令注入、记忆上下文注入、运行内视图稳定与签名推理块回放
3. [显式缓存优化器](#3-显式缓存优化器) — ExplicitCacheProcessor 断点策略
4. [缓存友好的上下文缩减](#4-缓存友好的上下文缩减) — 压缩的触发与让位、compress_min_save、动态阈值、缓存生命周期
5. [Pipeline 架构与缓存协同](#5-pipeline-架构与缓存协同) — 处理器执行顺序与缓存感知
6. [LLM 层集成](#6-llm-层集成) — cache_control 传递链路、缓存可观测性（四层监控）、性能特性、前缀缓存预热与空闲保活
7. [故障排查指南](#7-故障排查指南) — 常见问题诊断与解决方案
8. [代码索引](#8-代码索引)

---

## 1. 整体策略

框架采用**双层优化**架构：

```
缓存层（成本优化）                     质量层（上下文管理）
├─ 工具分层排序 (ToolLayer)            ├─ Filter（立即、可逆）
├─ System Prompt 冻结                  ├─ Compress（缓存热时推迟、可恢复）
├─ 时间戳注入到 HumanMessage           ├─ Summarize（最后手段、不可逆）
├─ 只增不改的消息历史                   └─ ThinkingBlockCleaner（清理无效 token）
├─ 显式 cache_control 断点
└─ 缓存热时推迟压缩（冷缓存排空）
```

**核心指标**：KV Cache 命中率。框架的每一个设计决策都围绕"不破坏前缀"展开。

---

## 2. 前缀稳定性保障

LLM API 的序列化顺序为 `Tools → System Prompt → Messages`。前缀匹配是 token 级别的——修改靠前的内容会使后续所有缓存失效。框架从三个维度保障前缀稳定。

### 2.1 工具分层排序（ToolLayer + ToolRegistry）

**理论依据**：工具定义位于序列化最前端，任何变化都会使全部缓存失效。

**实现**：

`tool_layers.py` 定义四层枚举（harness 三层 + EXTERNAL）：

```python
class ToolLayer(IntEnum):
    CORE = 1           # 始终存在，不可关闭
    HIGH_PRIORITY = 2  # 默认存在，前端可控制开关
    EXTENDED = 3       # harness 可选能力，按需 Turn1
    EXTERNAL = 4       # 框架外(server vendor / MCP direct / OpenAPI)
```

具体的工具层级注册：

| 层级 | 工具 | 常驻理由 |
|------|------|---------|
| **CORE** | web_fetch + file×3 + bash + glob/grep | 8 登记 | 通用 Agent 基线 | 不依赖搜索 API |
| **HIGH_PRIORITY** | web_search + memory×3 + skill_select | 5 登记 | 默认 bind web_search + memory×3 + skill_select | 组内搜索优先，记忆紧随，技能选择承接 |
| **EXTENDED** | 40 登记（仅 harness 可选能力） | 按需 Turn1（profile 开关） | todo_write / browser / wiki 等 |
| **EXTERNAL** | 6 登记（server vendor）+ 未登记 MCP/OpenAPI 动态工具 | Turn1 when mounted | x_search / MCP direct / OpenAPI |

`ToolRegistry.resolve()` 执行去重 + 排序：

```python
from myrm_agent_harness.agent.tool_management.tool_layers import get_tool_registry_sort_key

sorted_entries = sorted(
    best.values(),
    key=lambda e: get_tool_registry_sort_key(e.tool.name, e.layer or ToolLayer.EXTENDED),
)
```

排序规则：先按层级（CORE → HIGH_PRIORITY → EXTENDED → EXTERNAL）；HIGH_PRIORITY 层内按工具组优先级（web_search → memory → skill_select），同组内按名称字母序；EXTENDED 层按名称字母序；EXTERNAL 层按名称字母序（整段位于 harness 三层之后）。

**缓存效果**（API 顺序：`Tools → System → Messages`）：

```
第 1 轮: [CORE][HIGH_PRIORITY: web_search,memory,skill_select][EXTENDED: 无][System A][Messages…]
第 2 轮: [CORE][HIGH_PRIORITY: web_search,memory,skill_select][EXTENDED: +browser…][System A][Messages…]
          |← CORE+HIGH_PRIORITY Tools 仍命中 →| |browser 新算| |System A 重算|
```

**Tools 变化对 System 的影响**：Tools 位于 System **之前**，前缀为一条连续 token 链。EXTENDED 尾部增删/改 schema 时，变化点之后的 **System Prompt 无法复用旧 KV cache**（必须重算），即使 System 文本本身未改。ToolLayer 的价值是保护 **Tools 段内部**不变的前缀（CORE+HIGH_PRIORITY），而非让 System 在 Tools 变化时仍命中。

仅当 **Tools 段字节级完全一致** 且 System 链未变时，Tools + System 前缀才可同时命中；仅 Messages 追加时最常见。

### 2.1.1 Skill attenuation（MCP 溢出走 PTC，无 catalog proxy）

**原则（框架 11.1）**：严禁在 `awrap_model_call` 中 append 非 Turn1 工具 schema 到 `bind_tools`。

**MCP/OpenAPI 超 Turn1 预算**：整服 **MCP PTC**，见 `mcp_routing.py` + `TOOL_DESIGN_STRATEGY.md` §2.5（是否增加新的路由结局仍在评估，见 §10.2）。PTC 家族见 `toolkits/code_execution/EXECUTION_SYSTEM.md` § PTC 家族。

| 组件 | 路径 | 作用 |
|------|------|------|
| MCP 路由 | `agent/_factory/mcp_routing.py` | direct FC vs MCP PTC；单服 11,250 tok，aggregate 上限 15,000 tok |
| Skill attenuation | `middlewares/tooling/_skill_tool_choice.py` + `middlewares/tooling/skill_attenuation_middleware.py` | 技能加载后 `tool_choice.allowed_tools` 收窄；执行层 `check_trust_attenuation` |

**缓存效果**：Tools 前缀在长对话中保持稳定；discover 网关 description 无动态工具名嵌入；skill 加载后仍保持 Tools+System 前缀命中（`tool_choice` 变化仅影响 Messages 段，见 CONTEXT_ENGINEERING §6.2）。

### 2.2 System Prompt 冻结 + 时间戳注入到 HumanMessage

**理论依据**：在 System Prompt 中放入 `datetime.now()` 是最常见的缓存破坏原因。

**实现**：采用两层分离设计：

1. **System Prompt（框架层自动追加）**：`streaming/utils.py` 定义 `DATETIME_SYSTEM_RULES` 常量，`base_agent.py` 在 `_ensure_initialized()` 中自动追加到 system_prompt 末尾，业务层无需感知：

```xml
<datetime_rules>
Messages may contain timestamp tags: `[Sent at: YYYY-MM-DD HH:MM:SS (UTC±X)]` for historical messages (immutable, preserves Prompt Cache), or `<current_datetime>YYYY-MM-DD HH:MM Weekday (UTC±X)</current_datetime>` for the current message. Always use the latest `<current_datetime>` as your only "now" reference for all time-related reasoning.
</datetime_rules>
```

2. **HumanMessage（`streaming/message_builder.py`）**：语义分离标签

```python
# 历史消息：[Sent at: 2026-04-13 17:13:38 (UTC+8)]
# 输出示例：[Sent at: 2026-03-09 10:30:22 (UTC+8)]
prompt = f"[Sent at: {_format_time_with_timezone(dt, sent_timezone)}]"

# 当前消息：<current_datetime>2026-03-09 10:30 Monday (UTC+8)</current_datetime>
prompt = get_datetime_prompt(current_timezone)
```

`message_builder.py` 中将时间戳注入到 **HumanMessage**，使用不同标签区分语义：

```python
# 当前消息：使用 <current_datetime> 标签
messages[-1] = HumanMessage(content=f"{query}\n\n{datetime_prompt}")

# 历史消息：使用 [Sent at: ...] 标签，确保缓存稳定
dt = datetime.fromtimestamp(sent_at, tz=UTC)
time_str = _format_time_with_timezone(dt, sent_timezone)
prompt = f"[Sent at: {time_str}]"
messages[idx] = HumanMessage(content=f"{msg.content}\n\n{prompt}")
```

**关键设计**：

- **历史消息使用确定性时间戳**：同一 `ts + UTC offset` 永远产生相同输出，保证历史部分前缀 100% 命中
- **仅最后一条消息（新内容）无法缓存**——这是不可避免的
- **System Prompt 永远不包含动态内容**——完全冻结
- **说明文案与数据分离**：`datetime_rules` 在 System Prompt 中声明一次（被缓存），每条消息只携带 ~12 tokens 的时间戳数据，相比每条重复完整说明节省 ~28 tokens/条
- **核心行为规则**：`AGENT_CORE_RULES`（`streaming/agent_core_rules.py`）追加在 `DATETIME_SYSTEM_RULES` 之后。输出固定文本（反叙述 + 工具诚实 + 搜索与上下文复用），所有模型字节相同、与模型名无关，session 内不变，完全缓存安全。模型特有的失败模式不靠分厂商的提示词文本，由代码兜底（工具调用解析器、流恢复、CompletionGuard）
- **环境信息只在 bash 工具描述里**：OS 类型/版本/架构、Shell 类型/工具链差异、Python 工具链状态（pip/PEP-668/uv）与 VNC 视觉桌面提示由 `get_os_hint()`（`agent/meta_tools/bash/_tool/helpers.py`）拼进 bash 工具的描述，不进 system prompt；没挂 bash 工具的智能体不带这些信息。三类探测在进程生命周期内结果不变（`detect_platform()` 的 `@lru_cache(maxsize=1)`、`env_probe.get_environment_probe_line()` 的 `threading.Lock`、`get_environment_hint()` 的进程级缓存），正常环境省略 Python 与 VNC 部分（零额外 token）。完全缓存安全

**已知边缘情况 — Timezone 切换**：历史消息的时间戳使用**当前请求时的用户时区**渲染（`user_timezone_var.get()`）。如果用户在对话中途切换时区（如 `Asia/Shanghai` → `America/New_York`），同一条历史消息的 UTC offset 会变化（`UTC+8` → `UTC-5`），导致该消息之后的前缀缓存一次性失效。

这是有意的取舍：优先保证 LLM 看到用户当前时区的本地时间（功能正确性），接受极低频的缓存失效（用户很少在对话中途切换时区）。

### 2.3 Cron 定时任务场景的缓存分析

`app/core/cron/adapters/agent_runner/` 中的 `_SILENT_SUFFIX` 是一个典型的条件性内容注入：

```python
_SILENT_SUFFIX = (
    "\n\n---\n"
    "[Scheduler] This is a recurring scheduled task. "
    "If there is nothing actionable or noteworthy to report, "
    "respond with exactly `[SILENT]` (no other text) to skip notification delivery."
)

def _build_effective_prompt(job: CronJob) -> str:
    prompt = job.prompt or ""
    if job.schedule.kind in (ScheduleKind.CRON, ScheduleKind.INTERVAL):
        return prompt + _SILENT_SUFFIX
    return prompt
```

**缓存影响分析**（以每小时执行的 "检查服务器状态" 任务为例）：

```
第 1 次执行（10:00）：
[Tools: bash_code_execute_tool, file_read_tool, ...]                       ← 缓存命中 ✅
[System Prompt: 你是一个专业的 AI 助手...]                      ← 缓存命中 ✅
[HumanMessage: 检查服务器状态\n---\n[Scheduler]...[SILENT]
  <current_datetime>2026-03-09 10:00</current_datetime>]

第 2 次执行（11:00）：
[Tools: bash_code_execute_tool, file_read_tool, ...]                       ← 缓存命中 ✅
[System Prompt: 你是一个专业的 AI 助手...]                      ← 缓存命中 ✅
[HumanMessage: 检查服务器状态\n---\n[Scheduler]...[SILENT]
  <current_datetime>2026-03-09 11:00</current_datetime>]      ← 只有时间变了
```

| 部分 | 缓存命中？ | 原因 |
|------|-----------|------|
| Tools 定义 | ✅ | 完全不变 |
| System Prompt | ✅ | 冻结，不含动态内容 |
| `_SILENT_SUFFIX` | ✅ | 确定性常量，每次相同 |
| `<current_datetime>` | ❌ | 时间变化（不可避免） |

`_SILENT_SUFFIX` 是缓存安全的——它是确定性常量且位于 HumanMessage 中。如果把它放在 System Prompt 中，当任务类型从 `CRON` 变为 `ONCE`（无后缀）时，System Prompt 变化会导致后续所有缓存失效。

### 2.4 用户指令注入位置的缓存感知设计

`user_instructions_middleware.py` 将用户自定义指令注入为 SystemMessage。注入位置对跨用户缓存至关重要：

**设计**：注入到第一个 SystemMessage（system prompt）**之后**，而非之前。

```python
def _find_system_insert_idx(messages):
    for i, msg in enumerate(messages):
        if isinstance(msg, SystemMessage):
            return i + 1
    return 0
```

**缓存效果**：

```
[0] SystemMessage: system prompt          ← 跨用户缓存命中 ✅
[1] SystemMessage: <user_instructions>    ← 同用户缓存命中 ✅
[2] SystemMessage: <workspace_context>    ← 同对话线程内逐字节稳定（规则文件被编辑时才变）✅
[3] SystemMessage: `<user_memory_context>` ← 同用户缓存命中 ✅
[4] HumanMessage: ...                     ← 每轮变化
```

`<workspace_context>` 里的沙箱快照（`Git:` 状态、顶层文件列表）会随 agent 自己的改动变化，注入又只是对单次请求的 override、不写回图状态，若每次模型调用都重算，agent 一改文件位置 [2] 的字节就变，其后的前缀缓存在那次调用失效。因此快照按对话线程只生成一次：第一次发现线程里没有快照的模型调用在工作线程里生成它（限时 3 秒：超时的探测被抛弃，线程存下空串并冻结，此后不再探测、不注入快照块，位置 [2] 同样不动），并随这次调用的响应存入检查点状态的私有键 `workspace_snapshot` / `workspace_snapshot_root`（工作区变了才重新生成），之后每次调用读回同一份文本，约 250 token（`myrm-agent` 仓库实测 940 字符）；不用 `before_model` 之类的钩子节点，因为它会给每次模型调用多写一条检查点；规则文件仍每次实时读取。真实循环里的用例：`tests/agent/workspace_rules/test_middleware_run_scope.py`。

如果 `user_instructions` 在 system prompt **之前**（`insert(0, ...)`），不同用户的前缀从第一个 token 就不同，system prompt 的跨用户缓存完全失效。

### 2.5 记忆上下文注入的缓存感知设计

`middlewares/memory_context/memory_context_middleware.py` 把用户存储的记忆作为一个 `<user_memory_context>` `SystemMessage`（`# User Context (stable)`）插在连续 leading **SystemMessage** 链末端，与同用户前缀稳定对齐。块是请求局部的：每次模型调用都按本轮的记忆上下文重新生成并插入，不写回线程状态。本轮的记忆上下文在回合开始时定下：有记忆快照（`memory_brief_snapshot`）时读它；没有快照的运行在本轮第一次模型调用时读一次 `manager.get_context`，本轮后续调用复用这次结果，所以本轮内保存的记忆下一轮才进块。工具指引按每次调用绑定的工具挑选，挑选结果写进上下文的副本，所以同一轮内绑定的工具不变时各次调用的字节相同，记忆未被编辑时各轮之间也相同。

块只含用户配置的、变化很慢的条目（Profile、Rules、Self-Instructions、工作状态、工具指引）；已学习的事实不进块，由模型经 `memory_search_tool` 检索，前缀因此不随检索结果变化，也没有每请求随机的内容。

**冷/暖启动自适应**：新用户仅注入 `_COLD_START_CONTEXT`；老用户注入记忆块。

**RecallMode 控制**：`TOOLS` 模式跳过注入；`CONTEXT` 模式注入 context 但**不携带** Citation/Memory Search guidance（`memory_search_tool` 未绑定），cold-start 时整体跳过注入；`HYBRID` 模式注入 context 并携带完整 guidance tail。

前缀示意：

```
System: core prompt
System: `<user_instructions>` …
System: `<workspace_context>` …                 ← 同对话线程内 Stable（可无）
System: `<user_memory_context>` …             ← per-user Stable
Human: 用户第一句 …                             ← varies
System: `<data_boundary_rules>` …               ← SecurityBoundary，state 追加合并，首次模型调用后落在最新用户消息之后
```

**关键设计**

- **单一预算**：块内所有段落共享一次 `render_budgeted_sections`（`max_tokens=2500`，按段落优先级截断），块外没有第二份预算。
- **请求局部 + 标记判重**：块由消息标记 `additional_kwargs["memory_context"]` 识别，请求里已有带标记的块时才跳过（记 WARNING）；不按文本判重，因为数据边界规则、用户粘贴内容与工具结果都可能含 `<user_memory_context` / `<<<UNTRUSTED_DATA` 字样。块不写回线程状态，检查点里没有这个块的文本。
- **存储值先消毒**：条目经 `defang_markup()` 把每个标签起始符（ASCII `<`、全角 `＜`、小号 `﹤`）改写为 `&lt;` 后再进预算，存储值不能关闭记忆块或开出自己的 `<user_instructions>` 块；`&`、`>`、URL 和代码原样保留。改写是确定的，同样的存储值每次得到同样的字节，缓存前缀不受影响。
- **预算遥测**：`set_memory_runtime_budget` 的 `total` 是块预算折成的字符数（`max_tokens=2500` × 4，即 `MEMORY_BLOCK_BUDGET_CHARS`），`used` 是进入块的段落占用的字符数（被丢弃的段落不计），规则数含 VETO 与行为规则。

**业务侧入账 Human 前缀（IM + pipeline）**：`myrm-agent-server/app/core/utils/delivery_provenance.py` 提供统一横幅与 `resolve_general_agent_pipeline_labels`。IM 仍由 `app/core/channel_bridge/agent_executor/helpers.py::build_channel_inbound_query` 调用 `prepend_plain_banner`（支持多模态图片+文本）。HTTP/SSE `/agent-stream` LangGraph 主路径在 `general_agent/stream_pipeline.py::execute_stream_pipeline` **进入 `SkillAgent.run` 之前**：先 **INFO `general_agent_delivery_labels`**（`channel_label`/`ingress_label`），再 **`apply_general_agent_pipeline_banner`**；其中 `GeneralAgent.channel_name=="web_chat"`（默认入口，路由恒定）的用户消息不加横幅，日志标签仍记 `http_gui`/`browser_sse`，`cron`/`eval`/`headless_wakeup` 等照加并由其映射标签。**Headless wakeup** 在 `app/services/agent/wakeup_handler.py` 显式改写 `channel_name=headless_wakeup` 并在 `memory_channel_id` 缺省时 **写回 `web_chat`**，以免记忆分区随投递前缀漂移。FastLane 在 `myrm-agent-server/app/api/agents/general_agent/streaming.py` 使用 `apply_general_agent_pipeline_banner` + `GeneralAgentParams.channel_name`；FastSearch（`action_mode=="fast"`）走同一 GeneralAgent 管线，`workspaces_storage_root` 由 `app/ai_agents/general_agent/agent.py` 在构建 runtime context 时统一写入。群组上下文块仍仅在 IM executor 拼接。

### 2.6 只增不改的消息历史与单调前缀铁律（Append-Only Law）

框架遵循严格的"只追加不修改"（Append-Only）单调缓存原则：

- **压缩**使用紧凑格式**替换**工具结果内容，但不删除消息——消息结构（类型、顺序）保持不变
- **摘要**是唯一会改变消息结构的操作，作为最后手段触发
- 历史消息的时间戳一旦注入就不再修改（确定性注入）

#### 2.6.1 核心铁律：严禁回溯修改或剥离历史消息（Anti-Stripping Rule）

根据主流大模型提供商（Anthropic Claude、OpenAI 等）官方 Prefix Cache 规范及 Cache Diagnostics 准则：

> **Anthropic 官方黄金法则**：
> *"Treat the history as append-only; echo assistant content and tool results back verbatim."*
> *若历史消息数组中的任何前序消息被修改、重排、截断或剥离，将被诊断为 `messages_changed`，导致从变动点开始往后的所有缓存全部作废重算！*

**硬性约束**：
1. **严禁回溯剥离（In-place Strip）**：严禁在第 N 轮试图回头使用正则或文本替换，剥离/删除第 N-1 轮中注入的临时提示文本、提词板或引导语。这不仅无法“净化”上下文，反而会瞬间摧毁自该轮次以来的全部已缓存 Token（包括后续所有的 Assistant 思考与 Tool 结果）。
2. **状态更新走 Append-Only**：任务清单（Todo/Task/Progress）的流转与状态变更，天然应作为工具（如 `todo_write`）的执行结果以 `ToolMessage` 形式自然沉淀在对话流末尾；或通过后续轮次的新消息追加告知，绝不能向已缓存的历史消息“动刀”。
3. **原样回传（Echo Verbatim）**：发送给 API 的完整 `messages` 数组，历史部分必须保持字符级、字节级完全一致。

#### 2.6.2 对话线程所有权：线程是模型所见的历史，调用方的记录只在线程失效时重建它

LangGraph 线程保存模型实际看到的消息（含工具调用与结果），续接它才能保持前缀不变；调用方（server 的聊天库）保存用户看到的消息。两者同时往同一个线程里喂会让历史翻倍（`add_messages` 给每条喂入的消息新 id，不去重）。调用方经 `context["history_mode"]`（`runtime/context/session/session_continuity.py`）声明谁拥有对话，`agent/_internals/turn_history.py` 在每个新消息回合开始时解析：

| 模式 | 含义 | 喂入的消息 |
|------|------|-----------|
| `continue` | 线程仍与调用方记录一致 | 只有新消息；线程为空时自动降为 `replace` |
| `replace` | 线程失效 | 清空线程（清不掉则回合失败，不在旧线程上叠加），再喂调用方的 `chat_history` |
| `append`（缺省） | 调用方未接管线程卫生（IM / 定时 / 唤醒 / 一次性调用） | `chat_history` 叠加在线程之上，与既有行为一致 |

Resume 从不解析历史，线程原样续接，遥测记为 `history_mode=resume`。`replace` 会丢掉被丢弃线程里的工具轨迹，数量记入 `turn_context.history_discarded_tool_messages`。何时 `continue` 由调用方决定：server 用「活跃分支 + 压缩摘要」的摘要（`chats.history_sync_token`），只在回合完整结束后写入，撤销、编辑、重新生成、切换兄弟、压缩、服务端追加的通知、失败或取消的回合都会让摘要失配而重建。

#### 2.6.3 运行内视图稳定与签名推理块回放

同一次运行里，每个模型请求都必须延续上一个请求：提供商按请求前缀缓存，Claude 回传的签名推理块（`thinking` / `redacted_thinking`）也只对写下它的那段前缀有效（块绑定系统提示、工具集、此前的每条消息和签发它的模型）。运行内改写前缀既让缓存失效，也让下一次回放被拒。

**运行期通知只有两种写法**（`agent/middlewares/_run_notices.py`）：

- 每个请求逐字节相同：`frozen_for_run` 在运行的首个请求渲染一次，之后原样复用（todo 焦点；目标焦点的计数在运行结束时才结算，同样整次运行不变）。
- 写一次后留在当时最后一条已存消息之后：`NoticeLedger`（熔断约束、MoA 顾问建议、完成复核指令），之后新增的通知追加在后面，已写入的不挪位，同一条不重复写。
  MoA 顾问建议写在那次调用的最后一条已存消息之后，完成复核指令写在被拦草稿之后；写下它们之后，这次运行的每个请求都带着它们，`per_iteration` 的建议逐轮累加。账本只活一次运行，下一次运行从空账本开始。

随回合变化的内容只放在用户亲写的最新消息尾部（`core/message_tail.py::append_block_to_last_user_message`），不放在其后的运行时通知上。谁算「用户亲写」由 `core/message_origin.py` 判定；压缩、锚点、摘要、工具治理、回合计数与笔记触发读同一条回合边界。

**签名块的捕获与回放**（块存在 `AIMessage.additional_kwargs["thinking_blocks"]`，`core/thinking_blocks.py` 定义形状）：

| 环节 | 行为 |
|------|------|
| 捕获 | Anthropic 与 Bedrock 的流式解码器在内容块结束时拼出完整块（`ThinkingBlockAssembler`：按服务商 content index 一块一份草稿，signature 与 redacted 数据原样保留），`StreamAggregator` 在最后一个分片上交出整张列表；非流式经 `convert_dict_to_message` |
| 回放 | `convert_message_to_dict` 把块写回助手消息；Anthropic 与 Bedrock 线路把块放在该轮内容之首，OpenAI 兼容线路在 `prepare` 里剥掉 |
| 待答轮策略 | 思考开启时，等待工具结果的最后一条助手消息必须以块开头；当前工具循环里有工具调用轮缺块时，该请求不带 `thinking`，不让整个请求撞 400（`anthropic_thinking.py`，Bedrock 共用同一判定） |
| 回合级清理 | `ThinkingBlockCleaner` 的 Anthropic 分支只保留用户最新消息之后的块，更早回合的块整体清除（保留下来的块须是签发链上连续的一段），清除后不再放回 |
| 辅助调用 | 优雅收尾调用与摘要调用的提示词与该会话不同，发送前先 `without_thinking_blocks`；其余辅助调用只用全新文本 |
| 估算 | `estimate_message_tokens` 计入回放的块文本 |
| 安全网 | `thinking_replay_guard_middleware`：提供商拒绝回放（`FailoverReason.THINKING_SIGNATURE`，覆盖四种 400 措辞：块的签名对不上、redacted 块的数据对不上、块被改过、工具轮丢了开头的块）时，请求副本去掉全部块重发一次，本次运行不再回放；请求是否带着签名块由 `core/thinking_blocks.py::carries_signed_blocks` 判定；执行器层的 `stream_recovery_oneshot` 一次性恢复保留为最后一道 |

**签名块在途时的运行内改写**：回合内被回放的块绑定此前的每条消息（含工具结果里的图片字节），所以块还要被回放期间只做必要的改写，可选的改写等到用户的下一条消息。「在途」由同一个谓词判定：用户最新消息之后有会被回放的块（`carries_signed_blocks`，守卫、媒体窗口、主动剪枝与压缩/摘要共用）；主动剪枝还要知道第一个块在哪里（`first_signed_index`）。

| 改写 | 签名块在途时 | 原因 |
|------|-------------|------|
| 媒体窗口（`MediaFilterProcessor`：视觉模型只保留最新 `RETAIN_MEDIA_MESSAGES = 2` 条带媒体的消息） | 让位，回合内的历史截图原样保留；用户的下一条消息结束回合后窗口生效，剥离写进消息本身，之后的请求不再带 | 窗口在回合内剥掉较早的截图，此后回放的块就被拒。请求里的媒体块超过 `MAX_MEDIA_BLOCKS_HELD = 20` 时窗口立即接管：Anthropic 对超过 20 张图的请求给每张图加严尺寸限制 |
| Cache-TTL 剪枝的冷缓存触发 | Anthropic / Claude profile 关闭（`CacheTtlPruneConfig.cold_cache_prune_enabled=False`，`infra/cache_policy.py`）：空闲过久或命中率偏低都不启动剪枝，上下文占比达到 `emergency_prune_ratio` 仍剪；其余型号族保持开启 | 剪枝只持续一个请求，下一个请求回到未剪的提示，在剪枝请求里签发的块随即被拒 |
| 主动工具结果剪枝（`ActiveToolResultPruneProcessor`） | 从回合里第一个签名块起，只对该块之前的消息剪枝，也就是写下该块的那个请求拿到的列表：此后回合内的每个请求，以及批准后的续跑（`is_resume`、HITL 会话），读到的剪枝结果与那个请求相同；回合中途新落出最近窗口的结果等到用户的下一条消息；运行时强制的剪枝（`force_prune`）照常 | 每个请求的剪枝视图由这一步重新生成，回合中途新出现的剪枝让此后签发的块被拒；服务端的执行缓存在聊天活跃期间复用代理，空闲 1800 秒、配置变化或进程重启后新建，续跑可能落在一条管线上，它的内存里没有上次剪过什么的记录，所以结果只由消息决定（归档路径由内容摘要命名，占位文本逐字节相同） |
| 压缩、摘要（未到窗口的 90%） | 让位：不论缓存冷热都不在回合中途压缩，欠债记入 `compaction_debt_pending`，由回合结束后的服务端后台排空和下一个回合的首个请求（那时没有块在途）偿还 | 缓存空闲超过 5 分钟后这两步原本会在回合中途压缩（默认 Compress 从 50% 窗口、Summarize 从 40% 窗口起算，`ContextConfig.compress_start_ratio` 可调），此后回放的块被拒 |
| 到 90% 的压缩与摘要、紧急剪枝、`MediaBudgetGovernor` 的体积整形 | 照常执行 | 不做会超出窗口或体积上限；被拒一次，守卫去块重发，本次运行不再带 `thinking` |

**钉住它的测试**：`tests/support/enforcing_anthropic.py` 是按提供商规则逐请求核验的类型化替身（块未知、块之前的提示变了、块序列有缺口、待答轮缺块，各拒绝一次）。下面的图级用例在这个替身上跑聊天模型、传输、适配器、中间件栈和上下文管线（`tests/support/signed_tool_loop.py`）；管线接了与服务端同样的归档回调，服务端接的其余回调（驱逐、快照、压缩前钩子、会话笔记、轻量模型）不在这套装配里；每个回合、每次续跑都是共用同一检查点的新 agent：服务端在聊天活跃期间复用代理，这套装配取的是管线内存里没有任何东西可依赖的那一侧，状态不会从一个流带到下一个。

- `tests/agent/middlewares/test_thinking_replay_shipped_stack.py`：流式与非流式各 21 个请求全部带 `thinking`、零拒绝；守卫重试场景恰好 1 次拒绝。
- `tests/agent/middlewares/test_run_view_stability_shipped_stack.py` 钉住通知的运行内稳定；`test_moa_advisor_signed_replay.py`（`user_turn`、`per_iteration`、`every_n`、`risk_triggered` 四种扇出策略）与 `completion/completion_guard/test_directive_signed_replay.py` 各跑三个回合的工具循环：顾问建议与复核指令写下之后，本次运行的每个请求原样带着它，每个请求都带 `thinking`、零拒绝。
- `test_media_window_signed_replay.py`：截图循环回放到最后一个块；媒体块超过 20 个时窗口一步接管；下一个回合退役窗口之外的截图且保持退役；不签名的线路沿用原窗口；批准等待十分钟后续跑不被拒。
- `test_idle_return_signed_replay.py`：空闲超过 TTL 后回到会话时不剪枝、提示不变，窗口快用完时仍剪枝、被拒一次由守卫治愈。
- `test_active_prune_signed_replay.py`：12 轮、每轮 16k 字符的回合全程带 `thinking`、零拒绝、没有新增剪枝；下一个回合的首个请求才显示剪过的历史，同样零拒绝；回合在批准处暂停、续跑在新建的 agent 与管线上读到的与暂停前一致。
- `test_idle_mid_run_signed_replay.py`：回合中途一个慢工具让缓存过期（时钟拨过 5 分钟），回合内不压缩、全程带 `thinking`、零拒绝；欠下的压缩在下一个回合的首个请求偿还。

对应的单元测试：`tests/agent/context_management/` 下的 `test_media_filter_in_flight.py`、`test_cache_ttl_prune_cold_gate.py`、`test_active_prune_in_flight.py`、`test_compaction_in_flight.py`。

**无法离线验证的部分**：真实接口按账号的校验强度、签名块的真实体积与缓存成本、回合内保留截图、关闭冷缓存剪枝、让位剪枝与压缩对真实成本的影响（让位后上下文在回合内持续增长到 90% 窗口或回合结束，多出的缓存读取与写入没有按真实计费测过）、5.x 隐式思考型号的待答轮规则、Bedrock 在合成续写轮之后的行为、回答质量的提升、生产环境的缓存断点翻转频率、预算压力（`eco_mode`）在回合中途开启时的表现（保留窗口随之变小，第一个块之前的剪枝结果与写下它时不同，会被拒一次并由守卫治愈，没有测过）。块里的签名文本不能被脱敏改写（改写会让签名失效）。

---

## 3. 显式缓存优化器

### 3.1 适用范围

`ExplicitCacheProcessor`（`pipeline/processors/cache_optimizer.py`）只处理需要显式 `cache_control` 标记的模型：

| 模型 | 是否处理 | 原因 |
|------|---------|------|
| Anthropic Claude | ✅ | 需要显式 `cache_control` |
| 阿里云 Qwen/DashScope | ✅ | 需要显式 `cache_control` |
| OpenAI GPT | ❌ | 自动前缀缓存 |
| DeepSeek | ❌ | 自动前缀缓存 |
| Google Gemini | ❌ | 自动前缀缓存 |

模型识别逻辑：

```python
def _needs_explicit_caching(self, model_name: str) -> bool:
    model_lower = model_name.lower()
    prefixes = ("anthropic/", "claude-", "qwen", "dashscope/", "openai/qwen")
    return any(model_lower.startswith(p) for p in prefixes)
```

### 3.2 四种断点策略

基于 Anthropic 官方文档的最佳实践：

```
断点位置 = {
    1. 第一个 System 消息后（必须） → 缓存系统提示词（跨用户共享）
    2. 每 15 content blocks（自动） → 防止超出 20-block lookback window
    3. 压缩边界后（按需）           → 保护压缩内容
    4. 最后一条消息（必须）         → 增量对话缓存（官方推荐核心）
}
```

**System 断点设在第一个 SystemMessage 的设计决策**：在 Sandbox 多用户场景下，消息结构为 `[system_prompt, user_instructions, memory_context, ...]`。断点设在第一个 SystemMessage（system prompt）而非最后一个，确保 system prompt 的缓存快照可被所有用户共享。如果设在最后一个 SystemMessage（memory_context），缓存快照会包含 per-user 内容，无法跨用户复用。

**20-block 保护**：Anthropic 系统只向前查找 20 个 content blocks。框架按**实际 content blocks 累积**计数（而非消息索引），每累积 15 blocks 设置一个保护性断点，预留 5 blocks 安全余量。

关键：一条 AIMessage 带 3 个 tool_use 产生 4 个 content blocks（1 text + 3 tool_use），而非 1 个。`_estimate_content_blocks()` 精确估算每条消息的 blocks 数，确保在工具密集场景下断点间距不超过 20 blocks。

**压缩边界感知**：当 `CompressProcessor` 执行压缩后，会在 `context.metadata["last_compress_boundary_index"]` 记录边界位置，`ExplicitCacheProcessor` 据此在压缩边界后设置断点，保护压缩后的内容。

### 3.3 智能断点保留

Anthropic/阿里云限制最多 4 个断点。当对话超长时，生成的断点可能超过 4 个。

保留策略：

```
预计断点: [0:System, 16, 32, 48, 64, 74:最后]

智能保留（最多 4 个）:
实际断点: [0:System, 16, 32, 74:最后]
          └────必须保留────┘  └──必须保留──┘
```

规则：
1. **System（第一个）**：永远保留 → 缓存系统提示词
2. **最后消息**：永远保留 → 增量缓存核心
3. **中间断点**：保留前 `max_breakpoints - 2` 个

最后消息的断点即使距离不足 `min_message_gap` 也无条件保留——丢失它会导致增量缓存完全失效。

### 3.4 断点间距离验证

#### Token 精确验证

框架使用实际 token 计算验证断点间距离，确保符合 Anthropic 1024 tokens 最小要求。

**实现方法**：

```python
# cache_optimizer.py
ANTHROPIC_MIN_CACHEABLE_TOKENS = 1024

# 计算区间 tokens
segment_tokens = estimate_messages_tokens(messages[prev_bp : curr_bp + 1])

if segment_tokens >= ANTHROPIC_MIN_CACHEABLE_TOKENS:
    validated.append(curr_bp)  # Token 距离充足，保留
elif message_gap >= self.min_message_gap:
    validated.append(curr_bp)  # Fallback: 消息数满足最小间隔
```

**设计理由**：
- **精确计算**：工具调用消息可能包含 5000+ tokens，实际计算避免估算误差
- **Fallback 策略**：短消息密集场景，消息数满足最小间隔时保留断点，防止超出 20-block lookback window
- **最后消息特殊处理**：无条件保留，即使距离不足（增量缓存核心）

#### 可观测性：预期缓存统计

框架计算预期可缓存的 tokens 数，用于日志输出：

```python
# 从开始到最后一个断点的所有消息
expected_cacheable_tokens = estimate_messages_tokens(messages[: last_breakpoint + 1])
total_estimated_tokens = estimate_messages_tokens(messages)

# 计算预期命中率
expected_hit_rate = expected_cacheable_tokens / total_estimated_tokens
```

日志输出示例（简洁格式）：
```
📊 [ExplicitCache] Breakpoints: 4 at [0, 15, 30, 45] | Expected Cache: 85%
```

### 3.5 cache_control 注入

在消息的 `additional_kwargs` 中注入标记，TTL 策略根据端点自动解析：

```python
# Anthropic 直连 / Google Vertex → 1h TTL（长任务执行不会因 5min 过期而 cache miss）
msg.additional_kwargs["cache_control"] = {"type": "ephemeral", "ttl": "1h"}

# 代理 / 未知端点 → 默认 5min TTL（保守策略，避免不兼容）
msg.additional_kwargs["cache_control"] = {"type": "ephemeral"}
```

**TTL 解析优先级**：
1. `metadata["cache_retention"] = "long"` → 强制 1h TTL（业务层显式配置）
2. `metadata["cache_retention"] = "none"` → 默认 5min
3. `metadata["base_url"]` 包含 `api.anthropic.com` 或 `aiplatform.googleapis.com` → 1h TTL
4. `base_url` 为空 + `model_name` 以 `anthropic/` 开头 → 1h TTL（`anthropic/` 前缀路由到 Anthropic 官方端点的推断）
5. 其他 → 默认 5min（保守策略）

注入前会创建消息副本，避免修改原始消息。

---

## 4. 缓存友好的上下文缩减

上下文缩减（Filter/Compress/Summarize）是必要的，但每次缩减都可能破坏缓存前缀。框架通过多种机制平衡缩减需求与缓存保护。

### 4.1 压缩的触发与让位（冷缓存排空）

**问题**：每次超过阈值就压缩，频繁破坏缓存。

**实现**：`CompressProcessor.should_process`（`compress_processor.py`）按顺序判断，任何一步拦下就不压缩：

| 步骤 | 条件 | 行为 |
|------|------|------|
| 1 | 上下文低于动态阈值（`ContextBudget.calculate_dynamic_thresholds`，见 §4.3；预算压力 `eco_mode` 下再乘 0.8） | 不压缩 |
| 2 | 连续无效压缩达到上限，且上下文未到窗口的 90%（§4.1.1） | 不压缩 |
| 3 | 上下文未到窗口的 90%，且缓存还热（上一次模型调用不足 5 分钟）或签名推理块还在途（§2.6.3） | 让位：把欠下的压缩记入 `compaction_debt_pending` |
| 4 | 其余情况 | 压缩；单次压缩能省的 token 不足 `compress_min_save` 时放弃（§4.2） |

`SummarizeProcessor` 在 `should_summarize` 判定需要摘要之后，让位规则与第 3 步相同。欠下的压缩由回合结束后的服务端后台排空（`ChatService.schedule_background_drain`，缓存转冷后离线摘要）和下一个回合的首个请求偿还；到 90% 窗口时无论如何都压缩。Resume 与 HITL 会话期间不压缩（§5.5）。

### 4.1.1 Anti-Thrashing 保护

**问题**：当上下文内容本身难以压缩时（如最近的工具调用都在保护范围内），压缩每次只能节省 <10%，却每次都破坏 Prompt Cache。

**实现**：`CompressProcessor`（`compress_processor.py`）与 server `compact_chat` 通过 `compression_anti_thrash_guard` 追踪连续无效压缩次数；streak 持久化在 `chats.compression_ineffective_streak`（server `ChatCompressionStreakStore`），failure cooldown 仍由 DB 兜底。

| 条件 | 行为 |
|------|------|
| `streak < 2` | 正常执行压缩 |
| `streak >= 2` 且 `tokens < 90%` | 跳过压缩，保护 Prompt Cache |
| `streak >= 2` 且 `tokens >= 90%` | 强制压缩（安全网，防止 OOM） |
| 某次压缩节省 `>= 10%` | 重置 streak 为 0 |

**与 Hot Cache Bypass 互补**：Hot Cache Bypass 保护「短时间内」的缓存（5 分钟窗口），Anti-Thrashing 保护「压缩效果差」时的缓存。两者覆盖不同场景，共同最大化 Prompt Cache 命中率。

### 4.2 compress_min_save 保护

**理论依据**：小清理节省的 token 可能不足以弥补缓存失效的成本。

**公式**（简化）：执行压缩当且仅当 `T_cleared > T_prefix × (1 - P)`

**实现**：`infra/schemas/` 中定义默认值：

```python
COMPRESS_MIN_SAVE_DEFAULT: int = 3000
# 假设 T_prefix=30k，按 90% 折扣估算：30k × 0.1 = 3k
```

`compactor.py` 中的检查：

```python
if potential_saved < min_save_threshold:
    logger.warning(f"[压缩] 预计节省 ({potential_saved}) < 最小阈值 ({min_save_threshold})，跳过")
    return messages, 0
```

### 4.3 动态阈值

`ContextBudget`（`infra/context_budget.py`）根据运行时状态动态调整阈值：

**动态 compress_min_save**（根据剩余空间）：

| 剩余空间 | compress_min_save 调整 | 策略 |
|---------|----------------------|------|
| > 50% | 100%（默认值） | 保守，保护缓存 |
| 20-50% | 60% | 适度激进 |
| 10-20% | 40% | 激进清理 |
| < 10% | 20%（最低 500） | 紧急模式 |

**动态 compress_threshold**（根据会话进度）：

```python
def calculate_dynamic_thresholds(
    self, turn_count, estimated_remaining_turns=DEFAULT_ESTIMATED_REMAINING_TURNS
):
    # 计算"紧张度" = 剩余空间 / 预估需要
    urgency = remaining_tokens / estimated_remaining_tokens

    if urgency > 2.0:    # 很宽松 → 使用默认阈值
    elif urgency > 1.0:  # 中等 → 降低到 80%
    elif urgency > 0.5:  # 紧张 → 降低到 60%
    else:                # 非常紧张 → 降低到 50%
```

**设计意图**：长对话提前触发压缩，避免积累过多后一次性大规模压缩（破坏大量缓存）。

### 4.4 压缩的可逆设计（遮罩而非删除）

`compactor.py` 将工具结果替换为紧凑格式，但**不删除消息**：

```
COMPACTED: web_search_tool
QUERY: Claude API pricing 2024
META: tokens_saved=5000 time=2024-12-20T15:30:00
[Tool result offloaded during context compression]
- archive_ref: {"version":1,"reference_type":"tool_result","archive_path":"...","restore_tool":"file_read_tool",...}
- archived_path: /persistent/.context/<session_id>/compacted/sha256/<prefix>/web_search_tool_<hash>_<size>.txt
- restore_tool: file_read_tool
- original_tokens: 5000
- original_chars: 20000
- restore: call restore_tool with restore_args when exact archived details are needed.
LIFECYCLE: Retained while session active (30d) or file accessed (14d)
```

**Tokens vs Blocks**：压缩替换了消息内容（tokens 大幅减少），但不删除消息对象。一条 ToolMessage 压缩前后都是 1 个 `tool_result` content block。因此**压缩减少 tokens，不减少 content blocks 数**。这意味着即使压缩触发，20-block 保护断点的间距计算仍然需要精确的 blocks 计数。

**缓存影响**：紧凑格式替换了消息内容，会破坏该消息之后的缓存。但由于：
1. 缓存热时让位（§4.1）减少了破坏频率
2. compress_min_save 确保每次破坏都值得
3. 消息结构不变（类型、顺序），前面的缓存不受影响

### 4.5 摘要、Session Notes 与缓存生命周期 (Context Compaction)

摘要（Summarize）和 Session Notes 是改变消息结构的操作，作为**缓存重置事件**。框架在阈值触发时执行 **上下文压缩 (Context Compaction)**，包含 U 型记忆保护与显式界定。

**触发机制**：
- **主动拦截**：到达主动健康阈值 `proactive_reset_threshold`（默认 Max 的 40%；可通过 `ContextConfig.compress_start_ratio` 由 Agent 配置自定义，有效范围 [0.20, 0.85]）时触发。
- **Session Notes 触发**：当后台异步生成的 Session Notes 达到阈值就绪时，零 API 触发压缩。

**U 型记忆保护与缓存重建（适用于 Summarize 和 Session Notes）**：
```
摘要前（47 blocks）：                    摘要后（~10 blocks）：
[0] System prompt                       [0] System prompt (受保护，永久存在)
[1] user_instructions                   [1] user_instructions (受保护)
[2] memory_context                      [2] memory_context (受保护)
[3] First HumanMessage                  [3] First HumanMessage (受保护)
[4] First AIMessage                     [4] First AIMessage (受保护)
[5-40] 历史消息（多轮对话）              [5] <memory-context> 系统汇总摘要（替换了 [5-35]）
[41] 最新 HumanMessage                  [6-9] 最近几轮（保留）
                                        [10] 最新 HumanMessage
```

**关键设计**：
- **显式系统隔离 (Fencing)**：摘要块采用 `<memory-context>` 包裹，并硬编码前缀 `[System note: The following is recalled memory context...]`。这彻底阻断了模型将“过去的摘要”误认为“当前用户指令”的幻觉。
- **100% 缓存继承**：由于生成的 `<memory-context>` 被严格插入在受保护的头部（System Prompt + 首轮对话）**之后**，即使发生摘要重置，占据最多 Token 的头部信息依然完全静止，**完美命中 Prompt Cache**。
- **结构化输出保证 (with_structured_output)**：由于摘要作为上下文的关键基石，不可出现 JSON 损坏或格式错误。框架不做正则表达式提取，而是用 LLM 的 `with_structured_output(StructuredSummary)` 机制强制输出符合 12 字段结构，避免上下文内容干扰导致摘要结构错乱。
- **服务端防并发控制 (Concurrent Compaction Lock)**：在多用户 / 多任务 Server 侧（`compact_chat`），同一 `chat_id` 的压缩操作由进程级 `asyncio.Lock` 保护。这防止了用户短时间内多次发起任务导致两个并行任务同时触发 `Summarize` 并写入相同的锚点，进而导致持久化内容被覆盖或历史上下文意外损坏。

### 4.6 工具保护机制

`ToolProtectionConfig`（`infra/schemas/`）定义哪些工具的输出不可被**过滤**：

```python
BUILTIN_PROTECTED_TOOLS = frozenset({"skill_select_tool", "todo_write", "file_read_tool"})
```

注意：保护只针对 Filter（不可逆），不针对 Compress（可逆）。压缩后 Agent 可以通过 `cat` 恢复原始内容。

---

## 5. Pipeline 架构与缓存协同

### 5.1 处理器执行顺序

`build_default_processors()`（`pipeline/engine.py`）定义统一的默认处理器链；
`create_default_pipeline()`、`context_pipeline_middleware.py` 和 Evolution pipeline
都复用这条链，避免不同入口出现不同的缓存行为：

```
ReasoningAnchorProcessor ← 提取思考链决策/约束锚点；注入尾部 Human 的块按用户轮冻结（工具循环里这条消息是请求的第一条，同一轮内各工具轮逐字节不变），工具调用前的推理不产生锚点
       ↓
ThinkingBlockCleaner     ← 清理历史非活跃 thinking blocks，减少无效 token
       ↓
VisionFallbackProcessor  ← text-only 主模型 + visionFallbackModel 时将 image block 转为文本（在 MediaFilter 剥离前）
       ↓
MediaFilterProcessor     ← 文本模型主动剥离 image/video/audio（避免 400 + 省 token）；视觉模型只保留最新 2 条带媒体的消息，签名块在途的回合内让位（至多 20 个媒体块）
       ↓
FilterProcessor                ← 大型工具结果 → 磁盘持久化 + 智能预览 + 文件引用
       ↓
ActiveToolResultPruneProcessor ← 消费感知型每步主动归档超 2048 tok 的已消费工具结果（零 API 成本、protected tools 豁免）；回合里出现第一个签名块之后，只对该块之前的消息剪枝（续跑同理）
       ↓
CacheTtlPruneProcessor         ← cache 过期时归档/裁剪旧工具结果（零 API 成本、结构化引用、预算化恢复）；Claude 路线只在上下文占比逼近窗口时启动
       ↓
SelectiveEvictionProcessor     ← 按标记驱逐提示、草稿等瞬态消息（零 API 成本，保持工具调用成对）
       ↓
PreCompactProcessor      ← 仅在装配了 `on_pre_compact` 回调时存在：压缩前召回持久记忆，并可取消或替换这次压缩
       ↓
CompressProcessor        ← 旧工具调用 → 紧凑格式（提取错误与定义，原文归档可恢复）；未到 90% 窗口时缓存热或签名块在途则让位
       ↓
SessionNotesProcessor    ← 笔记就绪时零 API 压缩；未就绪时自然透传
       ↓
SummarizeProcessor       ← 超大上下文 → 结构化摘要（最后手段）；未到 90% 窗口时缓存热或签名块在途则让位
       ↓
PostCompactionRereadProcessor ← 压缩后自动重读最近修改的文件注入上下文
       ↓
PostCompactionRefetchGuardProcessor ← 压缩后反复回读同一归档路径时，在尾部注入一次提示
       ↓
NormalizeProcessor       ← 内容标准化（清理空行、换行符）
       ↓
MediaResolverProcessor   ← 解析 URL/file 图片引用为 base64
       ↓
MediaBudgetGovernorProcessor ← 会话累计图片体积超预算时，从旧到新降采样、仍超再转成文字，已稳定的历史消息不再变化
       ↓
ExplicitCacheProcessor   ← 注入 cache_control 断点（最后执行）
```

**ExplicitCacheProcessor 在最后执行的原因**：它需要在所有上下文操作完成后，基于最终的消息列表计算断点位置。如果先注入断点再压缩，断点位置会失效。

### 5.1.1 Cache-TTL 归档恢复闭环

`CacheTtlPruneProcessor` 不只依赖时间推断缓存过期。Pipeline middleware 会优先读取业务层显式注入的 `ProcessorContext.metadata["cache_usage_feedback"]`；没有显式值时，使用 `cache_metrics_collector` 从当前请求内真实 provider response usage 累计出的 `CacheUsageFeedback`。该对象包含 `cache_hit_rate`、`cached_tokens`、`input_tokens`、`calls`：

- 热缓存：存在 `cached_tokens` 且命中率达到热阈值时跳过 TTL 裁剪，保护仍然有效的前缀。
- 冷缓存：调用次数或输入 tokens 达到稳定样本后，低命中率会提前触发旧工具结果裁剪，避免等待固定 TTL。`CacheTtlPruneConfig.cold_cache_prune_enabled=False` 的 profile（Anthropic / Claude）不因缓存看起来冷了而启动，只有下面的紧急剪枝会启动它（原因见 §2.6.3）。
- 安全阀：即使命中率判断为冷，仍必须满足上下文占比和可裁剪 token 门槛，避免为了很小收益破坏消息历史。

处理器执行时先在工作消息列表中生成替换后的 `ToolMessage`，再一次性提交到 `ProcessorContext.messages`。归档成功、soft trim 成功、offload 失败、预算延后分别进入 `TaskMetrics`。成功归档结果按 `chat_id`、工具名、`tool_call_id`、内容长度和 `content_sha256` 组成归档器（`ToolResultArchiver`）内的幂等键，缓存容量有界（512 条，淘汰最久未用）；运行时归档存储按会话、工具、原始内容哈希和原始字节数生成内容寻址路径，并在复用前校验 metadata、归档 payload 哈希和 schema-v2 restore-map sidecar。restore-map 由 runtime 层统一契约生成和读取，包含 `content_index`、推荐范围来源、路径归一化和行号边界校验；快速复用与写入复用都会自愈损坏、schema 不匹配或缺失的 restore-map sidecar。同一会话 retry 同一工具结果时保持 archive ref 和恢复路径稳定，且不会重复写入归档。无 `chat_id` 的匿名上下文不写入共享归档目录。失败结果不进入缓存，后续 retry 仍会重新尝试 offload。预算指标区分两类语义：`deferred_reasons` 只表示未修改消息的真实剪枝延期；归档写入预算不足进入 `archive_deferred_reasons`，若随后结构感知 soft trim 成功，则同时记录 `archive_deferred_soft_trimmed_reasons`；归档写入和归档复用分别进入 `archive_written_count`、`archive_reused_count`、`archive_bytes_written`、`archive_bytes_reused`。当会话内 pruning 净收益为负、refetch 比例达到配置阈值、typed restore 成本占比达到阈值，或 typed restore 后保留 ROI 低于阈值时，后续 pass 会提高裁剪阈值和最小可裁剪 token 门槛，避免同一会话在低收益归档/恢复之间震荡。接近硬上下文上限时，`emergency_prune_ratio` 会允许 cache-TTL 剪枝在 HITL / resume 状态下绕过热缓存保护执行，优先避免请求越过模型窗口。

归档写入回调返回 `ContextOffloadResult`，用 `temporary_failure`、`permission_denied`、`quota_exceeded`、`unsupported` 区分失败类型；失败类型以 `offload_failure_kinds` 进入 `CompressionEvent` 与 `TaskMetrics`。归档引用由 `ContextArchiveReference` 生成，除路径、哈希、原始 token/字符数外，还带轻量 `content_index` 和可直接传给文件读取工具的 `chunk_restore_args`：

- `line_count`、`chunk_size_lines`、`chunk_count` 用于判断是否需要分段恢复。
- `chunk_ranges` 只暴露行号范围，不复制原文。
- `chunk_restore_args` 暴露前 12 个分块的 `path:start-end` 参数；恢复阻断事件还会携带 `restore_range_hints`，用 `error_keyword`、`section_heading`、`code_block`、`table_range`、`list_range`、`fallback_chunk` 等原因标记推荐范围，鼓励 GUI 和模型按结构恢复而不是整文件回读。
- JSON 对象会通过 `content_features` 暴露受限数量的顶层 key 名，JSON 数组会暴露长度，帮助模型定向读取字段或分段扫描数组。
- Markdown 标题、代码块、表格和列表项只暴露结构类型、数量和行号范围，便于 GUI 和模型推荐最小恢复范围，不把正文重新塞回上下文。

恢复读取由文件工具执行层统一拦截 `.context/{session_id}/compacted/` 路径，并在暴露内容前校验会话归属、整文件恢复 token 上限、单路径读取次数和单任务恢复 token 上限。整文件读取先用文件大小估算触发预算硬闸；如果文件大小探测失败，执行层返回 `archive_restore_size_probe_failed` 阻断，不暴露归档正文。范围读取继续通过 `chunk_restore_args` 的 `path:start-end` 参数恢复；typed GUI/server restore 读取靠后的大行号范围时会在归档旁生成并复用稀疏 byte-offset 行索引，同一归档的晚段恢复从最近行锚点 seek，避免从文件开头线性扫描。预算失败时返回稳定的结构化 blocked payload，而不是自然语言错误；payload 包含 `type`、`reason`、`archive_path`、`estimated_tokens`、`message`、`suggested_action`，并扁平输出恢复指引字段 `reason_label_key`、`severity`、`primary_restore_arg`、`recommended_ranges`、`restore_range_hints`、`content_features`、`guidance_source`、`fallback_reason`。恢复指引优先读取 schema 合法且行号范围有效的 restore-map sidecar；schema v2 sidecar 必须携带 `content_index`，所有支持的 sidecar 都必须通过统一路径和行号校验；sidecar 缺失、不可读或无效时返回固定分段范围和明确 fallback reason。同时写入 `TaskMetrics.archive_restore_blocked_count` 和 `ArchiveRestoreBlockEvent`，GUI 和上层 Agent 可以据此提示用户缩小读取范围或继续使用摘要引用。聊天流中，`cache_ttl_prune` 会发出 `context_pruned` 状态步骤；成功 offload 后 `ArchiveSummaryService` 异步写入 EpisodicMemory checkpoint，并通过 `archive_checkpoint` 状态步骤和 operation ledger 通知 GUI。压缩前 `PreCompactProcessor` 会 scroll 最近 checkpoint milestone 注入 protected 尾部。工具拦截层会把 `archive_restore_blocked` payload 转发为结构化 `agent_status`，前端只消费结构化事件来展示 `archive_restore_blocked` 进度步骤和 toast。Session Analytics 的 `context_health.cache` 使用会话总量展示成本，但 retention observation 优先选取 dominant model 的 `modelBreakdown` 样本，并在无精确原始 key 时使用 provider 前缀归一后的唯一精确匹配；归一结果存在歧义时回退会话聚合，避免混合模型会话把主模型真实缓存命中稀释成聚合误判，也避免把不同 provider 的同名模型误合并。

归档范围恢复索引基准采用 200,000 行 UTF-8 文本，恢复第 199,500-199,700 行：无索引流式读取 142.45ms、峰值 25.2KiB；首次构建索引并读取 478.96ms、峰值 188.2KiB；复用索引读取 2.85ms、峰值 129.3KiB。索引复用路径用于频繁读取同一大归档的靠后行号范围，首次构建成本由同一归档的多次范围恢复摊销。

### 5.2 处理器间的缓存协同

**CompressProcessor → ExplicitCacheProcessor**：

压缩处理器在执行后记录压缩边界：

```python
context.metadata["last_compress_boundary_index"] = boundary_idx
context.metadata["compression_count"] = compression_count
```

显式缓存处理器读取压缩边界，在该位置设置保护性断点：

```python
compress_idx = context.metadata.get("last_compress_boundary_index")
if compress_idx is not None and compress_idx not in breakpoints:
    breakpoints.append(compress_idx)
```

**ThinkingBlockCleaner → 缓存效率**：

清理历史消息中的 `reasoning_content` / `thinking_blocks`，减少无效 token 占用。按模型和消息类型智能处理：
- Anthropic：清理 `reasoning_content`；`thinking_blocks` 只保留在当前回合（用户最新消息之后），更早回合的签名块清除（见 §2.6.3）
- DeepSeek/MiMo/Kimi 等 thinking 模型：选择性清理 `reasoning_content`——API 仅要求 tool_calls 消息保留 reasoning_content，纯文本回复的历史 reasoning_content 安全删除
- 其他模型：清理 `thinking_blocks`，保留 `reasoning_content`

间接提升缓存效率——更少的 token 意味着更晚触发压缩，更少的缓存破坏。典型 DeepSeek 会话可节省数万 tokens。

### 5.3 中间件集成

`context_pipeline_middleware.py` 将 Pipeline 集成到 Agent 的中间件链中：

```python
context = ProcessorContext(
    messages=messages,
    llm=llm,
    metadata={
        "model_name": model_name,   # 用于 ExplicitCacheProcessor 判断是否需要处理
        "turn_count": turn_count,   # 用于 CompressProcessor 动态阈值
        "compression_intent": _extract_compression_intent(merged_ctx),  # 外部压缩焦点
    },
)
result = await current_pipeline.process(context)
```

Pipeline 按 `max_context_tokens` 缓存实例，避免重复创建。
`ContextPipeline.process()` 会在存在 `chat_id` 或当前任务上下文已设置 chat id 时持有 session-level context lock，确保同一会话的 Filter / CacheTtlPrune / Compress / Summarize 等消息变更串行提交；匿名上下文不创建全局默认锁，跨会话 pipeline 仍保持并行。`acquire_context_lock()` 对同一 asyncio 任务可重入，允许业务层已有锁保护时继续调用 pipeline 而不死锁。
压缩规划阶段额外遵循两条缓存友好约束：
- 只压缩完整的 `tool_call_id` 工具调用组，避免因压坏工具对而触发后续失败重试
- 不完整工具调用直接跳过，宁可少压一点，也不破坏 Prompt Cache 与消息结构稳定性
- `compression_intent` 只传递小体积结构化信号（如 `focus_files`、`focus_modules`、`failed_tool_call_ids`、`user_goal_hint`），避免把长文本业务语义注入稳定前缀而破坏缓存
- `failed_tool_call_ids` 已接入 Filter（结构 trim 保留失败输出）、Compress 优先级规划：失败工具调用即使输出内容看起来“像成功”，也会被提升为高优先级，减少错误恢复链路被过早 Filter 摘要或 Compress 压缩的概率
- `focus_files` / `focus_modules` 已接入 Filter 与 Compress 的 group 级优先级/retain 规划：Filter 与 Compress 共用同一套 tool_call args + 结果窗口扫描匹配逻辑，避免路径仅出现在 tool args 时被 Filter LLM 摘要
- `user_goal_hint` 已接入 Filter 与 Compress 的 group 级匹配：当缺少明确文件/模块路径时，仍可根据稳定目标关键词保护相关工具调用组，Filter 侧同样走结构 trim 而非 LLM 摘要

### 5.5 Resume-Aware Cache Preservation（HITL专用）

**设计目标**：当Agent从`interrupt()`恢复时，保持历史messages完全不变，确保Prompt Cache命中率95%+。

**核心原则**：
1. **只追加，不删除**：Resume时绝对不修改历史messages
2. **HITL会话期间禁用Compress**：避免多次HITL交互时破坏cache

**实现机制**：

**1. ProcessorContext增强**
```python
@dataclass
class ProcessorContext:
    # ...
    is_resume: bool = False  # Resume from interrupt()
    merged_context: dict[str, object] = field(default_factory=dict)  # 访问hitl_session_active
```

**2. BaseProcessor统一规则**
```python
def _should_skip_for_cache_preservation(self, context: ProcessorContext) -> bool:
    if context.is_resume:
        return True  # Resume时跳过
    if context.merged_context.get("hitl_session_active"):
        return True  # HITL会话期间跳过
    return False
```

**3. 修改性Processor行为**

| Processor | Normal | Resume | HITL会话期间 |
|-----------|--------|--------|-------------|
| VisionFallbackProcessor | ✅ 图像转文本 | ❌ 完全跳过 | ❌ 完全跳过 |
| MediaFilterProcessor | ✅ 剥离媒体（签名块在途的回合内让位） | ❌ 完全跳过 | ❌ 完全跳过 |
| FilterProcessor | ✅ 过滤 | ❌ 完全跳过 | ❌ 完全跳过 |
| ActiveToolResultPruneProcessor | ✅ 剪枝（回合里第一个签名块之后，只对该块之前的消息剪枝） | 有签名块在途时按同一规则剪枝，其余跳过 | 同 Resume |
| CompressProcessor | ✅ 压缩 | ❌ 完全跳过 | ❌ 完全跳过 |
| SessionNotesProcessor | ✅ 更新 | ❌ 完全跳过 | ❌ 完全跳过 |
| SummarizeProcessor | ✅ 生成 | ❌ 完全跳过 | ❌ 完全跳过 |
| ExplicitCacheProcessor | ✅ 所有断点 | ✅ 仅最后一条 | ✅ 正常 |

**4. Resume流程**

```python
# base_agent.py
if isinstance(query, Command):  # Resume模式
    merged_context["is_resume"] = True

# context_pipeline_middleware.py
is_resume = merged_ctx.get("is_resume", False)
context = ProcessorContext(
    messages=messages,
    is_resume=is_resume,
    merged_context=merged_ctx,
)

# 上下文溢出检测
if is_resume and total_tokens > max_context_tokens:
    raise ValueError("Resume failed: context overflow")
```

**5. HITL Session管理（业务层）**

```python
# myrm-agent-server/app/services/agent/stream_session/orchestrator_turn_body.py
if request.resume_value is not None:
    params.context["hitl_session_active"] = True  # 标记HITL会话活跃
```

**缓存效果**：

| 场景 | Before | After | 提升 |
|------|--------|-------|------|
| 单次HITL Resume | 0% | 95%+ | ♾️ |
| 多次HITL交互 | 0% | 90%+ | ♾️ |
| Resume成本 | $3.00/M | $0.30/M | 90% ↓ |
| Resume TTFT | 2000ms | 800ms | 60% ↓ |

**配套工具**：
- 错误恢复清理：Resume失败时自动清理checkpoint（业务层实现）

---

## 6. LLM 层集成

### 6.1 cache_control 传递链路

```
ExplicitCacheProcessor                    模型传输层（toolkits/llms/transport）
  │                                         │
  ├─ msg.additional_kwargs["cache_control"]  │
  │  = {"type": "ephemeral", "ttl": "1h"}   │  ← Anthropic 直连/Vertex 时
  │  = {"type": "ephemeral"}                 │  ← 代理/未知端点时（默认 5min）
  │                                         │
  └─────────────────────────────────────────→ API 请求中携带 cache_control
                                              （Anthropic Messages 线路写入 content block；
                                              OpenAI 线路只在声明支持的服务商保留，其余剥离）
```

`llm.py` 中的注释明确了设计决策：

```python
# 显式缓存（Claude/Qwen）完全由 Pipeline 的 ExplicitCacheProcessor 控制
# 传输层只透传标记，不自行注入断点
# 这样可以实现更智能的多断点策略
```

**为什么传输层不注入断点**：框架需要的是多断点策略（System + 压缩边界 + 20-block 保护 + 最后消息），断点位置取决于上下文管线的状态，只有 `ExplicitCacheProcessor` 知道；传输层不持有这些状态，只按消息里已有的标记转换请求。

### 6.2 自动前缀缓存模型

OpenAI / DeepSeek / Gemini 使用自动前缀缓存，无需显式标记。框架对这些模型的优化是**隐式的**——通过工具分层排序、System Prompt 冻结、缓存热时推迟压缩等策略保持前缀稳定，自动享受缓存折扣。

### 6.3 缓存效果可观测性

框架在三个层次追踪缓存命中情况：

#### 层次 1：断点设置预期（ExplicitCacheProcessor）

在设置断点时，计算预期可缓存的 tokens：

```python
expected_cacheable_tokens = estimate_messages_tokens(messages[: last_breakpoint + 1])
total_estimated_tokens = estimate_messages_tokens(messages)
expected_hit_rate = expected_cacheable_tokens / total_estimated_tokens

# 日志输出
📊 [ExplicitCache] 断点: [0, 15, 30, 45] | 预期可缓存: ~8500 (85.0%)
```

#### 层次 2：会话级缓存效果统计（token_tracker.py）

累积追踪整个会话的 token 使用量，并在会话结束时计算总体缓存效果：

```python
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0       # 缓存命中的 token 数
    reasoning_tokens: int = 0
    
    def get_cache_effectiveness(self) -> dict[str, float]:
        """计算会话级缓存效果"""
        cache_hit_rate = self.cached_tokens / self.prompt_tokens
        
        # 成本节省（相对于无缓存场景）
        original_cost = self.prompt_tokens * 1.0
        actual_cost = self.cached_tokens * cache_read_ratio + (self.prompt_tokens - self.cached_tokens) * 1.0
        cost_savings_pct = (original_cost - actual_cost) / original_cost
        
        return {
            "cache_hit_rate": cache_hit_rate,
            "cost_savings_pct": cost_savings_pct,
            "cost_savings_absolute": original_cost - actual_cost,
        }
```

在会话结束时（`base_agent.py`），自动输出累积统计：

```
💰 [Session Cache Summary] Calls: 12 | Hit Rate: 85.3% | Cost Savings: 81.0% (7738 tokens)
```

`utils/token_economics/usage_fields.py::extract_cached_tokens()` 从传输层统一后的 `usage` 中提取缓存命中数，支持所有提供商。统一发生在传输层边界（`toolkits/llms/transport`）：Anthropic 与 Gemini 的解码器写入 `prompt_tokens_details.cached_tokens`，OpenAI 兼容线路在 `openai_chat.py` 把顶层的缓存读取数（DeepSeek 的 `prompt_cache_hit_tokens`、网关转发的 `cache_read_input_tokens`）同步写入同一字段，提供商已给出的非零值不会被覆盖：

| 提供商 | 原始字段 | 传输层统一映射 |
|--------|---------|-----------------|
| OpenAI | `prompt_tokens_details.cached_tokens` | `prompt_tokens_details.cached_tokens` |
| Anthropic | `cache_read_input_tokens` | `prompt_tokens_details.cached_tokens` |
| Gemini | `cachedContentTokenCount` | `prompt_tokens_details.cached_tokens` |
| DeepSeek | `prompt_cache_hit_tokens` | `prompt_tokens_details.cached_tokens` |

#### 层次 3：单次调用命中率与成本节省（utils/logger.py）

每次 LLM 调用在详细日志路径下显示缓存命中率与相对「全部按普通 input 计价」的节省比例。数值由 ``utils/token_economics/cache_economics.compute_prompt_cache_stats(prompt_tokens, cached_tokens, cache_read_ratio=0.1)`` 计算；NDJSON 指标与 ``TokenUsage.get_cache_effectiveness()`` 使用同一函数。

语义要点：普通 input 计价系数 1.0，cache read 计价系数通过 ``cache_read_ratio`` 参数化（默认 0.1 匹配 Anthropic，OpenAI 为 0.5）；不纳入首次 cache write 的加价项（与 §6.3 下文说明一致）。

```python
stats = compute_prompt_cache_stats(prompt_tokens, cached_tokens)
cache_hit_rate = stats["cache_hit_rate"]
cost_savings_pct = stats["cost_savings_pct"]
```

日志输出示例：

```
📥 LLM API Response:
  Token Usage:
    - Prompt Tokens: 10000
    - Cached Tokens: 8530
    💾 Cache Hit Rate: 85.3% | Cost Savings: 81.0%
```

**成本节省公式说明**（相对于无缓存场景）：
- 无缓存成本 = 10000 × 100% = 10000 单位
- 有缓存成本 = 8530 × 5% + 1470 × 100% = 426.5 + 1470 = 1896.5 单位
- 节省 = (10000 - 1896.5) / 10000 = 81.0%

**注意**：此计算不包含首次创建缓存的 125% 成本（一次性支付）。实际长期使用中，创建成本会被后续多次命中摊平。

通过三层可观测性，开发者可以：
1. **设置时预期**：断点是否合理，预期命中率
2. **会话级累积**：整体缓存效果，总成本节省
3. **单次调用实际**：即时验证命中率和成本节省

**完整的监控流程**：
```
Turn 1: 
  📊 [ExplicitCache] Expected Cache: 0%    ← 首次无缓存
  📥 LLM Response: Cached: 0 tokens         ← 首次创建缓存

Turn 2:
  📊 [ExplicitCache] Expected Cache: 85%   ← 预期 85% 命中
  📥 LLM Response: Cached: 8530 tokens      ← 实际 85.3% 命中
  💾 Cache Hit Rate: 85.3% | Cost Savings: 81.0%

Turn 12 (会话结束):
  💰 [Session Cache Summary] Calls: 12 | Hit Rate: 85.3% | Cost Savings: 81.0% (7738 tokens)
                                                                          ← 会话总成本节省
```

#### 层次 4：可选 NDJSON 指标落盘（生产分析）

设置环境变量 ``MYRM_CACHE_METRICS_DIR`` 指向可写目录后，每次 ``log_llm_response`` 追加一行 JSON（NDJSON），按 UTC 日期写入 ``cache_metrics_YYYY-MM-DD.ndjson``。未设置该变量时不写盘、不进行文件 I/O。

**配对语义**：``context_pipeline_middleware`` 在每次模型调用开始时执行 ``clear_pending_explicit_cache_snapshot()``；``ExplicitCacheProcessor`` 在成功注入 ``cache_control`` 后执行 ``set_pending_explicit_cache_snapshot()``；``try_persist_cache_call_metrics`` 在记录本次响应时 ``take`` 并清空 pending，与**同一次** LLM 响应的 ``usage`` 合并写入。无显式缓存路径（未注入断点）时 ``explicit_cache_snapshot`` 为 ``false``，仍写入 ``usage`` 相关字段。

**记录字段（``schema_version`` = 1）**：

| 字段 | 含义 |
|------|------|
| ``recorded_at_utc`` | ISO8601 时间戳（UTC） |
| ``response_model`` | 响应中的模型名 |
| ``prompt_tokens`` / ``completion_tokens`` / ``cached_tokens`` | 来自传输层统一后的 ``usage``（仅支持 int/float/None，其他类型抛出 TypeError） |
| ``cache_creation_tokens`` | 本次调用写入提供商提示缓存的 token 数（``usage`` 没有报告时为 0） |
| ``actual_cache_hit_rate`` | ``compute_prompt_cache_stats`` 返回的 ``cache_hit_rate``（``prompt_tokens <= 0`` 时为 0） |
| ``cost_savings_pct_vs_uncached_input`` | ``compute_prompt_cache_stats`` 返回的 ``cost_savings_pct``（与 §6.3 层次 3 一致） |
| ``explicit_cache_snapshot`` | 本次是否与显式缓存 pending 配对成功 |
| ``prefix_shift`` | 可选；仅在本次请求改动了更早的消息（前缀不再延续上一个请求）时出现：``first_index``（第一条不同的消息）、``previous_length`` / ``current_length``、``kind``（``rewritten`` 改写 / ``truncated`` 尾部被截）、``announced``（上下文管线是否声明过这次改写，如压缩与剪枝；``false`` 表示请求自己改了历史） |
| ``explicit_cache`` | 可选；仅含核心缓存指标：``turn_count``、``breakpoint_count``、``message_count``、``total_estimated_tokens``、``expected_cacheable_tokens``、``compression_count``（预期命中率可通过 ``expected_cacheable_tokens / total_estimated_tokens`` 实时计算） |

**部署与配置**：

- **单实例语义**：默认 ``threading.Lock`` 假定单框架实例。多实例部署（如水平扩展）时，**控制平面必须**为每个实例注入不同的 ``MYRM_CACHE_METRICS_DIR``（例如 ``/logs/metrics/instance-1``），或将数据路由到统一的日志聚合器，以避免多进程交错写入导致 NDJSON 格式损坏。并发写入经过严格测试：20线程高竞争场景下吞吐量>500写入/秒，``threading.Lock`` 确保原子追加，无数据损坏或记录丢失。
- **定价参数**：cache read 倍数通过 ``cache_read_ratio`` 参数化（默认 0.1 匹配 Anthropic 90% off，OpenAI 为 0.5 即 50% off），调用方按需传入。
- **异常检测**：``compute_prompt_cache_stats`` 自动钳制 ``hit_rate`` 到 [0, 1]。当 ``cached_tokens > prompt_tokens`` 时（``hit_rate > 1``），记录 WARNING 日志并钳制为 1.0，提示提供商 ``usage`` 异常。

**NDJSON记录示例**：

```json
{
  "schema_version": 1,
  "recorded_at_utc": "2026-03-20T12:00:00Z",
  "response_model": "claude-3-5-sonnet-20241022",
  "prompt_tokens": 10000,
  "completion_tokens": 50,
  "cached_tokens": 8530,
  "actual_cache_hit_rate": 0.853,
  "cost_savings_pct_vs_uncached_input": 0.81035,
  "explicit_cache_snapshot": true,
  "explicit_cache": {
    "turn_count": 2,
    "breakpoint_count": 4,
    "message_count": 10,
    "total_estimated_tokens": 10000,
    "expected_cacheable_tokens": 8500,
    "compression_count": 0
  }
}
```

记录大小：约496字节（实际大小取决于字段值长度）

**口径差异与解释**：

- **Expected vs Actual**：NDJSON 中预期命中率 ``expected_cacheable_tokens / total_estimated_tokens`` 为 ``ExplicitCacheProcessor`` 基于**静态消息序列**的预期值；``actual_cache_hit_rate`` 为提供商 ``usage`` 返回的真实命中率。
- **差异原因**：预期值假定无 KV-cache 漂移、无工具结果插入（严格前缀匹配）；实际值受消息对象变更、工具结果写入、系统压缩影响。持续高差异（实际远低于预期）提示架构漂移（参见 ``CONTEXT_ENGINEERING.md`` 的 Manus 指标警告）。

**字段设计原则**：

- **核心指标优先**：仅保留与缓存性能直接相关的指标（``turn_count``、``breakpoint_count``、``message_count``、token统计、命中率预估、压缩次数）
- **职责单一**：专注缓存性能指标，模型信息通过 ``response_model`` 获取，业务追踪（chat_id/user_id）通过日志聚合实现，配置常量（断点参数）属于文档而非数据

#### 层次 5：缓存断裂预防+诊断（Always-on）

**预防层**：``toolkits/mcp/schema.normalize.canonicalize_schema_for_cache()`` 在 MCP 工具注册时对 ``inputSchema`` 做确定性 key 排序 + ``required``/``dependentRequired`` 集合排序，消除 MCP server 重连/重启后 schema 字段顺序抖动导致的前缀失配。

**诊断层**：``cache_break_detector.py`` 提供自动的缓存断裂检测和归因，独立于 NDJSON 持久化（always-on）。

**两阶段架构**：

1. **Pre-call**（``context_pipeline_middleware``）：``record_prompt_state()`` 计算 system prompt hash 和 model name，对比上一轮检测变化
2. **Post-call**（``try_persist_cache_call_metrics``）：``check_cache_break()`` 比较 ``cached_tokens`` 与上一轮值

**断裂判定**：``cached_tokens`` 下降 >5% 且绝对值 >2000 tokens。

**归因维度**：

| 维度 | 检测方式 |
|------|---------|
| ``system prompt changed`` | SHA-256 hash 对比 |
| ``model changed (A → B)`` | 模型名直接对比 |
| ``tools changed (+N/-N tools)`` | 工具列表 hash + 数量差异 |
| ``tool schema changed (tool_name)`` | 逐工具 hash diff |
| ``likely 5min/1h TTL expiry`` | 两次调用间隔推测 |
| ``likely server-side`` | 所有客户端指标不变，<5min 间隔 |
| ``message N rewritten (A → B messages)`` / ``history truncated (A → B messages)`` | ``request_view_guard_middleware`` 记录每个请求各消息的摘要（``infra/prefix_chain.py``，不含 ``cache_control`` 断点），与上一个请求比较，指出第一条不同的消息（或尾部被截）；NDJSON 的 ``prefix_shift`` 另带 ``announced`` 区分压缩、剪枝等有公告的改写与请求自己的改动 |

#### 技能目录与 Cache

| 内容 | 位置 | Cache 维度 |
|------|------|------------|
| Bound 技能 XML（含 MCP `mcp_*_skill`） | 首条 HumanMessage ``<bound_skills hash hidden_count>`` 基线（``skill_catalog_delivery.py`` + ``get_metadata_summary()``），只在对话（重）建时写入、之后永不改写；续接线程上 bind 漂移时在**新** HumanMessage 前置 ``<bound_skills_update hash>``（完整当前清单，声明取代此前所有清单，``agent/_internals/skill_catalog_turn.py``）；线程已投递的清单由线程自身消息读出，压缩抹掉区块后下一轮自动重新投递；bound 集指纹变化时同步 ``skill_search_tool`` 索引（stream+resume 同源）| messages[] 尾部；基线前缀字节不变。越过内联阈值会挂载/卸载 ``skill_search_tool``，工具数组随之变化（``turn_context.tools_signature_changes`` 计数） |
| skill_select_tool 静态规则 | ``skill_select_tool.description``（无 embed XML、无 skill 名；``skill_search_tool`` 提示经 dynamic_hints + weave 条件注入） | tool schema 前缀跨 Profile 稳定（≤20 内联 bind 时不挂载 search） |
| MCP 函数文档 | skill workspace ``/mcp/.../*.md``；经 ``skill_select_tool`` 返回 ToolMessage | 对话消息，非 system/tool schema |
| Active todo focus | ``progress_middleware`` 追加到当前轮 HumanMessage（瞬时/尾部） | 保证 system prefix cache；**注意**：后续轮次严禁回溯剥离已缓存轮次，否则触发 ``messages_changed`` |
| Session Notes 摘要 | ``SessionNotesProcessor`` 注入 **HumanMessage** | 不破坏 cache |
| Summarize 摘要 | ``SummarizeProcessor`` 注入 **HumanMessage** | 不破坏 cache |
| 记忆上下文 | ``memory_context_middleware`` **SystemMessage**（请求局部：每次调用按本轮记忆上下文重建，不写回线程状态） | 同一轮内绑定的工具不变时各次调用字节相同；只有记忆快照重建后才反映记忆的编辑（计为 ``system prompt changed``），会话中的记忆写入另经 ephemeral delta 追加到最新 Human 尾部，不动 System 前缀 |

**单工具 invoke 规则（2026-07-23 增补）**：

| 规则 | 说明 |
|------|------|
| 位置 | harness ``toolkits/*/`` 工具的 **description + args schema**；**禁止**迁入 ``AGENT_CORE_RULES`` / 全局 System Prompt |
| Token | **搬迁不省 token**（API 顺序 ``Tools → System → Messages``，同文本换段前缀总长不变）；只有 **压缩** description 才省 |
| 跨工具行为 | 「何时该搜」等跨工具规则可留 ``agent_core_rules.AGENT_CORE_RULES`` |
| 门禁 | ``tests/architecture/test_tool_prompt_placement.py`` + ``measure_turn1_token_inventory.py`` |
| 例外 | ``web_search_tool`` 保留长 description（中下等模型 query 调优）；**禁止**再迁入 System 或进一步瘦身，除非重做 golden eval |

``SkillMetadata.always=True`` 表示 **始终出现在首条 HumanMessage ``<bound_skills>`` catalog**（``always="true"`` 属性），**不是**写入 SystemMessage。

MCP 本身不直接改 SystemMessage；常见 ``system prompt changed`` 来自 planner 的首轮 one-shot 注入、memory 注入内容的变化（首轮建立、记忆快照重建后反映了编辑）等，而非 MCP 协议或 skill_select 目录变更。

**压缩感知**：``CompressProcessor``、``CacheTtlPruneProcessor``、``SessionNotesProcessor``、``SummarizeProcessor`` 执行后均调用 ``notify_compaction()`` 重置基线，避免压缩后的正常缓存重建被误报为断裂。

**生命周期**：通过 ContextVar 管理（与 ``TokenTracker`` 同层次），``init_cache_break_detector()`` 在 ``base_agent.py`` 中与 ``init_token_tracker()`` 一起初始化。

**NDJSON 集成**：当 ``MYRM_CACHE_METRICS_DIR`` 启用时，断裂事件记录在 ``cache_break`` 字段中：

```json
{
  "cache_break": {
    "prev_cache_read": 10000,
    "curr_cache_read": 3000,
    "token_drop": 7000,
    "reasons": ["system prompt changed"],
    "cache_creation_tokens": 8000
  }
}
```

### 6.4 性能特性

框架缓存系统的性能开销经过严格基准测试验证，确保在生产环境中的影响可忽略不计。

**ExplicitCacheProcessor 开销**（排除日志输出）：

| 上下文规模 | 延迟范围 | 阈值 | 相对 LLM API 延迟 |
|-----------|---------|------|------------------|
| 小（10消息） | 1.8-3.9ms | <5ms | <0.5% (vs ~1s API) |
| 中（50消息） | 10-21ms | <25ms | <2.5% (vs ~1s API) |
| 大（150消息） | 37-45ms | <50ms | <5.0% (vs ~1s API) |

- **should_process 早退**：非 Anthropic 模型的过滤检查 <10μs（常量时间字符串匹配）
- **吞吐量**：30消息上下文处理吞吐量 100-266调用/秒（平均 ~150调用/秒）

性能范围基于多次运行实测数据（受系统负载影响）。所有阈值设置均包含缓冲以确保生产环境稳定性。

**NDJSON 并发写入性能**：

| 场景 | 吞吐量 | 数据完整性 |
|------|--------|-----------|
| 20线程高竞争 | >500写入/秒 | 100%（threading.Lock 原子追加） |
| ContextVar 线程隔离 | N/A | 100%（无跨线程泄漏） |

证据来源：``tests/agent/context_management/test_cache_processor_performance_benchmark.py``（5个基准测试）、``tests/agent/context_management/test_cache_metrics_concurrent.py``（5个并发测试）

### 6.4 前缀缓存预热与空闲保活

``preheat.py`` 提供三种前缀缓存保护机制（仅对显式缓存提供商 Anthropic/Qwen 生效）：

| 机制 | 触发时机 | 实现 |
|------|---------|------|
| Agent Init Preheat | ``BaseAgent._ensure_initialized()`` 末尾 | ``schedule_init_preheat`` — fire-and-forget ``asyncio.Task``，用户打字时预热 |
| Post-Compaction Preheat | 上下文压缩后 | ``preheat_prefix_cache`` — 由 ``idle_tasks._run_context_compaction`` 调用 |
| Idle Keep-Alive | 空闲 ≥4min 时每 4min 一次 | ``CacheKeepAliveManager._loop`` — 防止 5min TTL 过期 |

**Keep-Alive 工作原理**：

```
用户活跃期间             空闲期间（>4min）           用户恢复
   │                       │                        │
   ├─ touch() ←─ run()     ├─ sleep(240s)           ├─ touch() ←─ run()
   ├─ touch() ←─ run()     ├─ send probe            │  (keepalive 暂停)
   │                       ├─ sleep(240s)           │
   │                       ├─ send probe            │
```

- 零副作用：probe 不经过 ``context_pipeline_middleware``，不触发 ``cache_break_detector``
- fail-open：异常仅 ``debug`` 日志，不阻断正常流程
- 成本：~$0.09/天/session（每次 probe ~10 input tokens，无 output tokens）

---

## 7. 故障排查指南

### 7.1 缓存命中率为 0

**现象**：日志显示 `Cache Hit Rate: 0.0%`

**可能原因**：

1. **模型不支持 Prompt Cache**
   - 检查：模型是否为 Claude/Qwen 系列（需要显式 cache_control）或 OpenAI/Gemini/DeepSeek（支持自动前缀缓存）
   - 解决：
     - 对于 Claude/Qwen：检查日志中是否有 `📊 [ExplicitCache] Breakpoints` 消息，确认断点已注入
     - 对于 OpenAI 等：确认使用最新版本的 API（如 `gpt-4o-2024-08-06`），旧版本可能不支持

2. **首次调用（创建缓存）**
   - 说明：首次调用时缓存为空，只能创建缓存，无法命中
   - 正常：第二次调用开始才会有缓存命中
   - 验证：查看后续调用的 `cached_tokens` 是否增加

3. **消息序列变化（破坏前缀匹配）**
   - 原因：前缀缓存要求**严格的前缀匹配**，任何前序消息的变化都会导致缓存失效
   - 检查：对比两次调用的 `messages` 前缀是否完全一致（包括空格、标点、顺序）
   - 解决：确保前序消息不变，只追加新消息

4. **Token 数不足最小阈值**
   - 原因：Anthropic 要求每个断点至少 1024 tokens（Claude Sonnet/Opus 4.x）
   - 检查：日志中的 `Expected Cache: 0%` 提示未达到最小阈值
   - 解决：增加消息长度或等待对话累积足够 tokens

### 7.2 Expected vs Actual 差异大

**现象**：NDJSON 记录中计算的预期命中率（`expected_cacheable_tokens / total_estimated_tokens`）与 `actual_cache_hit_rate` 差异超过 20%

**可能原因**：

1. **架构漂移（动态内容注入）**
   - 原因：框架假定消息序列静态，但可能有动态内容注入（如时间戳、随机 ID）
   - 检查：对比实际发送的消息与预期消息是否一致
   - 解决：确保动态内容注入到 `user_message` 而非 `system_prompt` 或前序消息

2. **工具结果插入**
   - 原因：工具调用后插入工具结果消息，改变消息序列结构
   - 说明：这是正常行为，工具结果无法提前预测
   - 预期：差异通常 <10%，如果 >20% 则可能有问题

3. **压缩触发**
   - 原因：`CompressProcessor` 把历史工具结果换成紧凑格式，改写了该位置之后的前缀（tokens 减少，block 数不变，见 §4.4）
   - 说明：压缩后会重置部分缓存（符合设计）
   - 验证：检查 `compression_count` 是否递增

4. **提供商 usage 异常**
   - 原因：`cached_tokens > prompt_tokens`（数据不一致）
   - 检查：NDJSON 中 `actual_cache_hit_rate > 1.0`（未钳制时）
   - 解决：联系提供商确认 API 返回的 `usage` 字段正确性

### 7.3 NDJSON 未生成

**现象**：设置了 `MYRM_CACHE_METRICS_DIR` 但未生成 NDJSON 文件

**可能原因**：

1. **环境变量配置错误**
   - 检查：确认环境变量名称拼写正确：`MYRM_CACHE_METRICS_DIR`
   - 验证：打印 `os.environ.get("MYRM_CACHE_METRICS_DIR")` 确认值已设置
   - 解决：确保在进程启动前设置（重启服务）

2. **目录权限不足**
   - 原因：指定的目录不可写
   - 检查：日志中是否有 `Failed to append cache metrics` 错误
   - 解决：确保目录存在且进程有写权限（`chmod 755`）

3. **LLM 调用失败**
   - 原因：`log_llm_response` 未被调用（LLM 调用失败或被拦截）
   - 检查：是否有 LLM 响应日志
   - 解决：确保 LLM 调用成功完成

4. **多实例写冲突**
   - 原因：多个实例写入同一目录，导致文件损坏
   - 检查：NDJSON 文件格式是否正确（每行独立 JSON）
   - 解决：为每个实例配置不同的 `MYRM_CACHE_METRICS_DIR`（如 `/logs/metrics/instance-1`）

### 7.4 缓存命中率突然下降

**现象**：原本 >80% 的命中率突然降到 <20%

**可能原因**：

1. **System Prompt 变化**
   - 原因：修改了 system prompt 或用户指令
   - 影响：破坏所有缓存前缀
   - 解决：避免频繁修改 system prompt；必要时通知用户缓存将重建

2. **模型切换**
   - 原因：切换到不同的模型（如 `claude-3-5-sonnet` → `claude-3-opus`）
   - 影响：不同模型的缓存不共享
   - 说明：这是正常行为

3. **会话重置**
   - 原因：新开会话或清空历史
   - 说明：新会话从零开始，首次调用无缓存命中

4. **提供商缓存 TTL 过期**
   - 原因：Anthropic 缓存 TTL 为 5 分钟（代理端点）或 1 小时（直连端点，框架已自动配置）
   - 影响：超过 TTL 未调用，缓存失效
   - 解决：直连端点已自动使用 1h TTL；代理端点高频调用场景下不影响，低频场景接受缓存重建

### 7.5 性能调优参数

**场景：高级用户需要调整断点策略**

当前参数（`ExplicitCacheProcessor` 构造函数）：
- `safe_block_interval=15`：每 15 blocks 设置保护性断点
- `min_message_gap=6`：断点间最小消息数（fallback 策略）
- `max_breakpoints=4`：最大断点数（Anthropic/阿里云限制）

**调优方向**：

1. **提高缓存粒度**
   - 调整：`safe_block_interval=10`（更小）
   - 效果：更多断点，更细粒度的缓存
   - 代价：更多 cache write 成本（首次创建）

2. **降低缓存粒度**
   - 调整：`safe_block_interval=19`（更大）
   - 效果：更少断点，更粗粒度的缓存
   - 代价：缓存命中率可能降低（超出 lookback window）

**约束分析**：
- 默认值 `15` 基于 Anthropic 官方 20-block lookback window（留 5-block 缓冲）
- 修改阈值会影响缓存命中率和写入频率（trade-off：写入成本 vs 节省收益）
- 低于 10：写入频繁，成本增加；高于 18：超出 lookback window，命中率下降

---

## 8. 代码索引

### 前缀稳定性

| 文件 | 职责 |
|------|------|
| `tool_management/tool_layers.py` | CORE/COMMON/EXTENDED/EXTERNAL 四层定义 + 工具注册表 |
| `tool_management/registry.py` | `resolve()` 按 layer + name 排序，确保工具定义顺序确定性 |
| `streaming/utils.py` | `get_datetime_prompt()` 生成时间标签 + `DATETIME_SYSTEM_RULES` 系统规则常量 |
| `streaming/agent_core_rules.py` | 核心行为规则：`AGENT_CORE_RULES` 是所有模型共用的固定文本 |
| `streaming/message_builder.py` | `inject_datetime_tags()` 时间戳注入逻辑（当前消息 + 历史消息确定性注入） |
| `base_agent.py` | `_ensure_initialized()` 中追加 DATETIME_SYSTEM_RULES + AGENT_CORE_RULES + 渠道输出提示（`resolve_channel_output_hint`）到 system_prompt（canary 不进 system prompt：每会话随机的 token 会让前缀缓存在该处分叉，改由 `CanaryMiddleware` 作为跟在用户输入之后的独立 SystemMessage 注入） |
| `app/ai_agents/agent_middlewares/user_instructions_middleware.py` | 用户指令注入到 System Prompt 之后（跨用户缓存感知） |
| `workspace_rules/middleware.py` | Workspace 规则注入（user_instructions 之后、memory_context 之前） |
| `middlewares/memory_context/memory_context_middleware.py` | 记忆上下文注入位置的缓存感知设计 |
| `middlewares/_run_notices.py` | 运行期通知整次运行内保持位置与文本（`frozen_for_run`、`NoticeLedger`） |
| `core/message_tail.py` | 随回合变化的内容只写在用户亲写最新消息的尾部 |
| `core/thinking_blocks.py` | 签名推理块的形状、拼装、估算文本与剥离 |
| `middlewares/thinking_replay_guard_middleware.py` | 提供商拒绝回放的推理块时，去掉全部块重发一次 |
| `middlewares/request_view_guard_middleware.py` + `infra/prefix_chain.py` | 记录请求消息摘要，供缓存断点归因指出被改写的第一条消息 |
| `app/core/cron/adapters/agent_runner/` | `_SILENT_SUFFIX` 条件性内容注入（确定性常量，缓存安全） |

### 显式缓存

| 文件 | 职责 |
|------|------|
| `pipeline/processors/cache_optimizer.py` | `ExplicitCacheProcessor` — 断点计算、Token 距离验证、cache_control 注入 |
| `infra/cache_metrics_collector.py` | 可选 NDJSON 指标（``MYRM_CACHE_METRICS_DIR``）、ContextVar 与 LLM 响应配对 |
| `utils/token_estimation.py` | `estimate_messages_tokens()` — Token 计算（支持图片、工具调用等） |
| `tests/agent/context_management/test_cache_optimizer_unit.py` | 单元测试 — 断点计算、Token 验证、边界条件、注入逻辑（15个核心测试用例） |
| `tests/agent/context_management/test_cache_integration.py` | 集成测试 — 完整缓存链路（Processor → NDJSON 配对、Expected vs Actual 差异检测）（6个集成测试） |
| `tests/agent/context_management/test_cache_metrics_collector.py` | 单元测试 — NDJSON 落盘、pending 配对、无环境变量时不写盘 |
| `tests/utils/test_prompt_cache_economics.py` | 单元测试 — ``coerce_usage_non_negative_int``（int/float/None）、``compute_prompt_cache_stats``（自动钳制+日志） |
| `tests/agent/context_management/test_cache_processor_performance_benchmark.py` | 性能基准测试 — ``ExplicitCacheProcessor`` 开销验证（小/中/大上下文、should_process早退、吞吐量）（5个基准测试） |
| `tests/agent/context_management/test_cache_metrics_concurrent.py` | 并发测试 — ``threading.Lock`` 正确性、ContextVar 线程隔离、高竞争写入吞吐量（5个并发测试） |

### 缓存友好的上下文缩减

| 文件 | 职责 |
|------|------|
| `pipeline/processors/cache_ttl_prune_processor.py` | `CacheTtlPruneProcessor` — cache TTL 过期或接近硬上下文上限时将旧工具结果归档为结构化引用或结构感知裁剪 |
| `pipeline/processors/cache_ttl_prune_archive.py` | `ToolResultArchiver` — 经业务层回调把工具结果写入归档存储，同一会话、工具调用与内容只写一次，并在存储应答后通知业务层排入摘要 |
| `pipeline/processors/cache_ttl_prune_roi.py` | 剪枝收益回路 — 按会话已记录的指标抬高裁剪门槛（`effective_prune_policy`），并把本次剪枝写入 `TaskMetrics`（`record_prune_metrics`） |
| `pipeline/processors/cache_ttl_prune_helpers.py` | Cache TTL pruning helpers — 归档/裁剪 DTO、内容转换、占位符渲染、消息替换和归档写入预算判定 |
| `infra/archive_reference.py` | `ContextArchiveReference` — 对归档工具结果提供稳定 DTO、内容哈希、会话归属、结构索引和模型可读恢复提示 |
| `infra/cache_policy.py` | `CacheTtlPrunePolicy` — 按模型/供应商解析官方 TTL 校准 profile，并允许业务层注入覆盖；Anthropic / Claude profile 不因缓存看起来冷了而启动剪枝（`cold_cache_prune_enabled=False`） |
| `tracking/task_metrics.py` | `TaskMetrics` — 记录真实剪枝延期、归档预算延期、归档写入/复用、归档恢复读取成本、净节省和执行层恢复读取预算 |
| `pipeline/processors/compress_processor.py` | `CompressProcessor` — 压缩的触发判定（动态阈值、Anti-Thrashing、让位）与执行；未到 90% 窗口时缓存热或签名块在途则让位 |
| `pipeline/processors/active_tool_result_prune_processor.py` | `ActiveToolResultPruneProcessor` — 每步主动归档超阈值的已消费工具结果；回合里出现第一个签名块之后，只对该块之前的消息剪枝（`first_signed_index`），续跑同理 |
| `strategies/compactor/compactor.py` | 可逆压缩实现（紧凑格式 + 外部化到文件，减 tokens 不减 blocks） |
| `strategies/summary/summarizer/` | 结构化摘要（缓存重置事件，减 tokens 且减 blocks） |
| `infra/context_budget.py` | `ContextBudget` — 动态阈值计算 |
| `infra/schemas/` | `ContextConfig` — 阈值定义、`COMPRESS_MIN_SAVE_DEFAULT`、`COMPACT_RULES` |

### Pipeline 与集成

| 文件 | 职责 |
|------|------|
| `pipeline/engine.py` | `ContextPipeline` — 处理器链执行引擎 |
| `pipeline/processors/media_filter.py` | 文本模型主动剥离 image/video/audio（避免 400）；视觉模型只保留最新 2 条带媒体的消息，签名块在途的回合内让位 |
| `pipeline/processors/vision_fallback_processor.py` | text-only 主模型 + visionFallbackModel 时将 image block 转为文本（MediaFilter 之前） |
| `pipeline/processors/filter_processor.py` | 大型工具结果过滤（工具保护机制） |
| `pipeline/processors/summarize_processor/` | 结构化摘要（最后手段）；未到 90% 窗口时缓存热或签名块在途则让位 |
| `pipeline/processors/thinking_cleaner.py` | Thinking Block 清理（减少无效 token） |
| `middlewares/context_pipeline/context_pipeline_middleware.py` | 中间件集成入口 |
| `toolkits/llms/core/llm.py` | LLM 层 cache_control 传递说明 |
| `utils/token_economics/cache_economics.py` | ``coerce_usage_non_negative_int``（严格类型检查）、``compute_prompt_cache_stats``（自动异常日志，``cache_read_ratio`` 参数化） — 日志、NDJSON、``get_cache_effectiveness`` 使用统一计数与定价逻辑 |
| `utils/token_economics/tracker.py` | ``TokenUsage.get_cache_effectiveness()`` — 调用 ``compute_prompt_cache_stats`` |
| `toolkits/llms/utils/logger.py` | 单次调用缓存日志（coerce + ``compute_prompt_cache_stats``）；``log_llm_response`` 内触发可选 NDJSON |
| `agent/base_agent.py` | 会话结束时输出累积缓存统计 |

### 设计文档

| 文件 | 内容 |
|------|------|
| `context_management/CONTEXT_ENGINEERING.md` | 业界理论（Manus、Anthropic、Factory Research） |
| `docs/architecture/datetime-injection.md` | 时间戳注入 & Prefix Cache 设计 |

---

## ⚠️ 动态内容注入警告：SystemMessage vs HumanMessage

> **严格遵守规则**：禁止将任何运行时动态生成的内容追加为 `SystemMessage`。

### 规则说明

**为什么？**
- 动态内容（如子 Agent 通知、后台任务结果、实时时间戳）每次不同
- `SystemMessage` 变化会破坏 Prompt Cache 前缀，导致所有后续缓存失效
- 这会导致 **10x 成本增加**（95% 缓存命中率 → 0%）

**正确做法**：
- 动态内容 **必须** 使用 `HumanMessage`
- 静态、确定性内容才能使用 `SystemMessage`

**错误示例**（严重性：P0）：
```python
# ❌ 错误：动态内容作为 SystemMessage
messages.append(SystemMessage(content=dynamic_notification))
```

**正确示例**：
```python
# ✅ 正确：动态内容作为 HumanMessage
messages.append(HumanMessage(content=dynamic_notification))
```

### 动态内容的注入位置

框架内的动态内容都以 `HumanMessage` 或用户最新消息的尾部块进入请求，没有任何一处使用 `SystemMessage`：

1. **`_internals/agent_runtime.py::run_agent_loop`** — 运行开始时，文件恢复通知与上一轮遗留的子 Agent 通知（`stale_notifications`）以 `HumanMessage` 追加
2. **`progress_middleware.py`** — Todo focus 追加到用户最新消息的尾部（用户没写消息时作为运行时 `HumanMessage` 放在最后）；每次运行的首个请求渲染，之后原样复用，经 `request.override` 送出，不写回状态
3. **`middlewares/security/security_guardrail_middleware.py`** — Circuit Breaker 环境约束以瞬态 `HumanMessage` 经 `request.override` 送出，同一份约束清单只写一次
4. **`utils/token_economics/budget_boundary_middleware.py`** — 预算警告（每次运行一次）与最终作答提示（每个中间件实例一次）以带 `[SYSTEM INSTRUCTION]` 前缀的 `HumanMessage` 追加
5. **`citation_rules_middleware.py`**（server 层，`general_agent/agent_middlewares/`）— 本轮出现不可信外部来源时，引用规则以瞬态 `HumanMessage` 经 `request.override` 送出

流式阶段取走的子 Agent 完成通知只以 SSE 事件送达前端（`streaming/recovery/stream_recovery_continuation.py::_handle_subagent_notifications`），不写入模型上下文；运行开始时仍未取走的通知才由上面第 1 项追加为 `HumanMessage`。

### 开发者注意事项

**在添加新的动态内容注入时**：
1. 首先判断内容是否每次调用都可能变化
2. 如果是动态内容，**必须**使用 `HumanMessage`
3. 在代码中添加注释说明原因（写法参考上述注入位置）
4. **【反面避坑禁令】严禁“先注入、后剥离”的反模式**：
   - 不得为了追求“会话历史纯洁”而在下一轮次剥离前一轮注入的文本！任何对前序 `HumanMessage` 内容的修改都会触发 `messages_changed` 导致整段消息缓存彻底失效。
   - 任务清单（Todo/Task）状态演进优先采用 `ToolMessage` 原样追加（Append-Only）的标准实践，严禁搞 In-place 历史重写。
5. **输入侧护栏的改写必须对重复扫描字节稳定**：`middlewares/security/user_input_guard.py` 每次模型调用都会重扫 state 里的用户消息，所以任何改写都要保证“扫第二遍不再变化”。
   - 最新用户消息：在一次用户输入的**首次**模型调用里写入 PII 脱敏与安全告诫前缀，之后工具轮次看到的字节不再变化。用无状态的“首次调用”判定（用户消息之后还没有 AI/Tool 消息）保证告诫只前置一次，不靠往历史里加标记。
   - 更早的用户消息：历史随每轮再次送入模型，护栏按同一策略静默改写（PII 脱敏；注入 / 危险意图为 `fail_closed` 时拦截），不写审计、日志与告诫前缀。脱敏结果确定、假名按值稳定，故同一条消息作为最新消息与作为历史时的脱敏字节一致；默认策略（未启用隐私策略，注入 / 意图非 `fail_closed`）下完全不动历史。
   - 新增输入侧改写必须是确定的、对自身输出幂等（脱敏后的文本再脱敏不变），不动 runtime 追加的 `is_system_synthetic` 消息，也不在每次调用重复前置同一段文本。
   - 保证范围不含恢复路径：`streaming/recovery/stream_recovery_truncation.py` 的 `_try_text_continuation` 等处用**原始输入**重喂消息列表，重喂的原文不会被再次改写；续跑轮（审批后）的重驱动不重喂任何消息，只追加一条提示，前缀留在检查点里原样不动。

**文档引用**：
- 详见 `CONTEXT_ENGINEERING.md` § Prompt Cache Best Practices
- 参考 Anthropic Claude API 官方指南：[Dynamic content in user messages](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching#dynamic-content-in-user-messages)
- 参考 Anthropic Claude 官方诊断手册：[Cache diagnostics: messages_changed](https://platform.claude.com/docs/en/build-with-claude/cache-diagnostics)
