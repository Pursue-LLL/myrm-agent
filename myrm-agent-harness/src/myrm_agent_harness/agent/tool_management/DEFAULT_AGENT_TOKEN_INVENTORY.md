# 默认 Agent 初始 Token 逐项清单

> **术语**：下文 **「工具」= LLM 工具**（Action Tool）。§4.18 所列编排信号**不是** LLM 工具，不计入 LLM 工具总数（见文末 `TOOL_COUNT` 自动生成块）。

> 测量方法：`tiktoken o200k_base` 规划 SSOT（`utils/text_utils.PLANNING_ENCODING`；与 GPT-5 / GPT-4o 族一致）
> 测量时间：2026-09-16（`scripts/measure_turn1_token_inventory.py`）；`web_search_tool` 的描述（§三）于 2026-11-04 重测，`web_fetch_tool` 的描述（§二）及据此推出的 CORE 小计与 Turn-1 工具层合计于 2026-11-05 重测；`memory_save_tool` 的描述（§三）及据此推出的 HIGH_PRIORITY 小计与 Turn-1 工具层合计于 2026-11-12 重测；§一 的 `messages[0]` 各分量与合计、以及据此推出的各场景 System Prompt 层与小计，于 2026-11-09 按当前源码重测；§四 的 38 个 EXTENDED 工具与 §4.24 的 5 个 server 工具于 2026-11-04 重测：各工具经 `create_*` 工厂构造（后端用 stub，`image_tool` / `video_tool` 用引擎默认配置），取 `tool.description` 的 o200k_base token 数；`delegate_task_tool` 的描述含运行期 sub-agent 名册，只计固定部分；`image_tool` / `video_tool` 的描述含运行期模型名，数值随配置浮动；§4.18 编排信号不是 LLM 工具，沿用记录值；§四 各行都不由测试锁定
> 测量宿主：macOS 25.5.0 / arm64 / bash（bash 工具描述里的 OS hint、toolchain 探测行与 VNC 行随宿主变化，见 §二 标注）
> 测量对象：默认通用智能体，Turn 1 初始化时的完整 prompt 结构；`prompt_mode=full`、`enable_answer_tool=False`（server 默认）、locale EN（工具描述为主，prompt 主体见 §一 双列）
> 漂移门禁：`tests/scripts/test_measure_turn1_token_inventory.py` 锁定 Turn-1 默认 13 个工具（§二、§三）的逐工具数值，`tests/architecture/test_prompt_token_budget_gate.py` 锁定预算上限；server 仓 `tests/architecture/test_first_turn_static_prompt_budget.py` 按语言锁定静态首轮 system 消息
>
> **三 tier 计量**：① UI 上下文环 = 上一轮 API `prompt_tokens`；② compress / summarize / emergency prune 预算 = messages + bind-tools overhead（本表）+ 可选 max(API)；③ 非 OpenAI 模型 client 估算存在偏差，账单以 provider usage 为准。

---

## 一、System Prompt 层（`messages[0]` 拼装 + 跟随用户输入的 canary 与安全边界）

> **口径**：tiktoken `o200k_base` 实测（`utils/text_utils.PLANNING_ENCODING`），宿主 macOS。
> `messages[0]` 由框架层 `agent/base_agent.py` 的 `_ensure_initialized()` **一次拼装**完成——业务层 CORE prompt 只是其中一段，框架层在其后追加 3 段；widget 能力声明、安全边界与 canary 都是**独立 SystemMessage**（widget 在前导 system 消息之后，安全边界与 canary 跟在用户输入之后），不计入 `messages[0]`。

| # | 组件 | Token (o200k_base) | 来源文件 | 说明 |
|---|------|-------------------:|----------|------|
| 1 | CORE_SYSTEM_PROMPT | **600** (EN) / **786** (ZH) | `server/ai_agents/prompts/general_agent_prompt.py` | `prompt_mode=full` + `enable_answer_tool=False`（server 默认，`server/ai_agents/agent_params.py:147`）。开启 answer_tool 时为 676 / 868。组成 = identity + AGENT_RESPONSE_RULES + TASK_INTEGRITY（来自 `shared_rules.py`；搜索模式改用 SEARCH_RESPONSE_RULES） |
| 2 | DATETIME_SYSTEM_RULES | 89 | `harness/agent/streaming/utils.py:55` | 时间感知规则常量（`<datetime_rules>` 标签），冻结在 system prompt 中 |
| 3 | AGENT_CORE_RULES | **286** | `harness/agent/streaming/agent_core_rules.py` | 核心规则**无条件注入**，所有模型字节相同、与模型名无关：禁止叙述工具调用、工具结果诚实、断言缺失前先验证、搜索与上下文复用、原生 FC 约束 |
| 4 | channel output hint | 0（web_chat，网页聊天不声明）· 56（slack）· 52（voice）· 25（wechat）· 17（webhook）· 0（无渠道） | `harness/agent/streaming/channel_output_hints.py` | 按渠道名解析；命中 `CHANNEL_OUTPUT_HINTS` 常量表 |
| 5 | canary 指令（独立 SystemMessage，追加在最新用户消息之后） | **50~57**（均值 ≈53） | `harness/agent/security/detection/canary_guard.py:54` | `SECURITY CANARY: CANARY-<12 位 hex>`；随机 hex 触发 BPE 分裂，实测 300 次采样分布 50~57。由 CanaryMiddleware 每个对话线程注入一次（`agent/middlewares/security/canary_middleware.py` 的 `before_model`），线程已带 canary 指令就沿用；**不占用 `messages[0]`**，system prompt 因此在所有会话里字节相同 |
| 6 | SecurityBoundary 数据边界规则（独立 SystemMessage，追加在最新用户消息之后） | **299** | 定义于 `harness/core/security/detection/content_boundary.py:300`（`agent/security/detection/content_boundary.py` 为 re-export shim） | 由 SecurityBoundaryMiddleware 每次运行注入一次（`agent/middlewares/security/security_boundary_middleware.py` 的 `before_model`）；**不占用 `messages[0]`** |
| 7 | widget 能力声明（独立 SystemMessage，插在前导 system 消息之后、用户输入之前） | **348** | `server/ai_agents/agent_middlewares/widget_capability_middleware.py:23` | `<widget_capability>` 标签；WidgetCapabilityMiddleware 在每次模型调用的请求里插入（不写入对话状态），位置与字节恒定；仅 web_chat 渠道的 `prompt_mode=full` 挂载（`mount_resolver.mount_widget_capability`），搜索面、IM、定时、语音、看板、评测不挂 |

**`messages[0]` 合计（实测，含上表 1~4，不含运行时条件追加）**：

| 模型 | full-ZH | full-EN |
|------|--------:|--------:|
| 所有模型（核心规则与模型名无关） | **1,161** | 975 |

> 口径：`messages[0]` = CORE(full, locale, `enable_answer_tool=False`) + DATETIME 89 + AGENT_CORE_RULES 286（web_chat 无渠道提示），各分量分别计数后相加。
> `messages[0]` 的各分量在参数组合内字节恒定；canary 的随机 hex（50~57 tok）在独立消息里，不进 `messages[0]`。
>
> 默认组合（中文用户 + full）：`messages[0]` 1,161 + widget 能力声明 348 + 跟随用户输入的两条独立 SystemMessage（canary ≈53 + 安全边界 299）= **1,861 tokens**。
>
> **运行时条件追加**（默认不注入，按需叠加，不计入上表；均来自 `server/ai_agents/general_agent/factory/prompt.py` 的 `system_prompt +=` 分支）：
> `DESKTOP_CONTROL_RULES` 424（只有英文版，挂载桌面控制工具时追加，`mount_computer_use`）· `SEARCH_DEEP_SUFFIX`（search 深研模式）· unattended 声明 ~55 · `get_worker_lifecycle_guidance()`（kanban worker 模式）· `CHANNEL_NOTIFY_SYSTEM_APPENDIX`（通知工具挂载）· `[Mounted Workspace Directories]` 清单（session roots）。用户自定义指令不在 `system_prompt` 里，由 `user_instructions_middleware` 作为独立 SystemMessage 注入。

**`enable_answer_tool` 影响**（该 flag 在 `general_agent_prompt._PROMPT_MAPS` 预构建时二分，改变 CORE 主体本身）：full 模式 EN +76 / ZH +82，search 模式**无差异**。server 默认 `False`（`server/ai_agents/agent_params.py:147`），上表已按 False 计量。

**缓存特性**：`messages[0]` 与其后的工具块在参数组合内字节恒定，跨用户共享缓存；随机 hex 只出现在跟随用户输入的 canary 消息里。把它放进 `messages[0]` 时，前缀缓存在该 token 处就与其他会话分叉，其后的工具块（约 5k token）与整段历史每个会话、每一轮都要全价。同一个首轮请求的实测：canary 留在 system 消息里首轮缓存 0%，移到最后一条 system 消息后 90% 到 98%。

---

## 二、CORE 工具层（8 个；通用 Agent Turn1 bind 8 个，shell 启用时）

> 通用 Agent 基线：`web_fetch` + file×3 + bash×2 + glob/grep（`tool_layers.py:64-71`）。Fast 模式由 `resolve_agent_mount(WEB_FAST)` 关闭 file/bash。

| # | 工具名 | Token (tiktoken) | 来源文件 | 说明 | 加载条件 |
|---|--------|------------------:|----------|------|----------|
| 4a | web_fetch_tool | 92 | `harness/toolkits/web_fetch/web_fetch_agent_tools.py` | HTTP 抓取/深读（默认只读全文，含 PDF/DOCX/XLSX/PPTX；同时配置 reranker 与 embedding 时提供 fetch_and_extract，描述为 272）。描述不提浏览器工具：「只读优先 web_fetch」的路由提示只在浏览器一侧，挂载 `web_fetch_tool` 时由 `browser_navigate_tool` 的 Dynamic Hints 追加 | Turn1 基线 |
| 6 | **bash_code_execute_tool** | **1,412** | `harness/agent/meta_tools/bash/_tool/tool_description.py` + `_tool/helpers.py:54` | Shell/Python。**宿主相关**：静态描述 1,355（宿主无关）+ OS hint（含 `os_release`/`arch`，见 `platform.py:116-122`；macOS arm64 58 / ubuntu-latest 32 / 各发行版实测 31–60）+ 可选 toolchain 探测行（干净环境为 0）+ 可选 VNC 视觉桌面行（只有带 DISPLAY、x11vnc 与 websockify 的 Linux 沙箱才有，约 56，示意值，其余宿主为 0）。拼接处 BPE 合并使实测总数比两段之和少 1（1,355+58=1,413，实测 1,412） | 通用 Agent 基线 |
| 6b | **bash_process_tool** | **107** | `harness/agent/meta_tools/bash/bash_process_tools.py` | 后台进程 list/output/kill（CORE；与 bash_code_execute 同挂） | enable_shell_tools |
| 7 | file_edit_tool | 132 | `harness/agent/meta_tools/file_ops/file_edit_tool.py` | 批量 edits[] 原子编辑 | 通用 Agent 基线 |
| 8 | file_read_tool | 332 | `harness/agent/meta_tools/file_ops/file_read_tool.py` | 读取文件 | 通用 Agent 基线 |
| 9 | file_write_tool | 118 | `harness/agent/meta_tools/file_ops/file_write_tool.py` | 创建/覆盖写入 | 通用 Agent 基线 |
| 10 | glob_tool | 201 | `harness/agent/meta_tools/file_search/glob_tool.py` | 通配符搜索 | 通用 Agent 基线 |
| 11 | grep_tool | 205 | `harness/agent/meta_tools/file_search/grep_tool.py` | 正则搜索 | 通用 Agent 基线 |

**CORE 描述小计（Turn1）**：**2,599 tokens**（8 工具，macOS arm64 实测；`scripts/measure_turn1_token_inventory.py`）。Linux 宿主因 OS hint 更短而为 2,573（ubuntu-latest 口径）。

---

## 三、HIGH_PRIORITY 工具层（注册 5 个；高优层 · Default-ON, User-Togglable）

**架构定位**：生产级 Agent 的高优标配工具，**默认开箱即用 100% 开启（Default-ON）**，但允许用户在前端设置中按需手动关闭（User-Togglable，如无痕对话 `incognito_mode` 关闭记忆，或纯离线环境关闭网络搜索）。

默认 Turn1 bind：**web_search + memory×3 + skill_select**（`DEFAULT_ENABLED_BUILTIN_TOOLS` 含 memory；`todo_write` 与 `request_answer_user_tool` 默认不 bind，见各 opt-in 开关）。

组内排序（`get_tool_registry_sort_key`）：**web_search (Rank 0) → memory 块 (Rank 10~12) → skill_select (Rank 20)**。

| # | 工具名 | Token (tiktoken) | 来源文件 | 说明 | 加载条件 |
|---|--------|------------------:|----------|------|----------|
| 12 | **web_search_tool** | **1,134** | `harness/toolkits/web_search/_web_search_tool_description.py` | 网络搜索（EN/ZH LLM-facing query-rewrite SSOT；server 传 locale；web_fetch 提供 fetch_and_extract 时多一段推荐，描述为 1,174） | GUI 可关 |
| 13 | **memory_search_tool** | **110** (EN) / **122** (ZH) | `harness/toolkits/memory/agent_surface/_memory_search_description.py` | 统一检索：description 与 args schema 随 `MemorySearchPolicy` 派生，默认仅 memory corpus（schema 无 `corpus` / `expand_*`）；开启会话检索后 description 为 232（EN）/ 255（ZH） | enable_memory |
| 14 | **memory_save_tool** | **578** (EN) / **593** (ZH) | `harness/toolkits/memory/agent_surface/_memory_tool_texts_{en,zh}.py`（`_memory_agent_tool_descriptions.py` 组装） | 写入长期记忆（EN core；wiki/approval 动态段；保留原有关键 guardrail 短语） | enable_memory |
| 15 | **memory_manage_tool** | **289** (EN) / **348** (ZH) | 同上 | 更新/删除/纠正/评分；仅以 `memory_id` 寻址（类型由已存记忆决定，无 `category` 参数）；correct→knowledge only（preserves history）；update→措辞微调；**user-locked rule 不可 update/delete** | enable_memory |
| 16 | **skill_select_tool** | **334** (EN) / **388** (ZH) | `harness/agent/meta_tools/skills/select/skill_select_tool.py` | 字节稳定静态 rules，按 locale 选 EN/ZH 常量；bound catalog 在首条 HumanMessage `<bound_skills>`，漂移以 `<bound_skills_update>` 尾段下发 | skill_backend present |

**HIGH_PRIORITY 描述小计（Turn1，EN 描述）**：**2,445 tokens**（5 工具；web_search + memory×3 + skill_select；默认 memory_search 仅 memory corpus）

---

## 四、EXTENDED 工具层（harness 可选；EXTERNAL 在其后）

### 4.1 glob/grep（归属 CORE 层）

glob_tool / grep_tool 登记在 CORE 层，Turn1 与 file 工具一并 bind。见 §二。

### 4.3 历史会话搜索（opt-in，由 memory_search_tool 承载）

历史聊天检索通过 `memory_search_tool` 的 `corpus=sessions` ACL 启用（用户开启 `memoryEnableConversationSearch` 且非无痕）。`conversation_search/` 模块为 sessions corpus 执行后端；框架不提供独立的 `conversation_search_tool`。

### 4.3 技能工具（有技能后端时加载）

| # | 工具名 | Token (tiktoken) | 来源文件 | 说明 |
|---|--------|------------------:|----------|------|
| 21 | skill_manage_tool | 263 | `harness/agent/meta_tools/skills/manage/skill_manage_tool.py` | 创建/修改/删除技能 |
| 22 | skill_search_tool | 277 | `harness/agent/meta_tools/discover_capability/discover_capability_tool.py` | 统一能力发现；**条件绑定**（hidden_skill_count > 0）；描述随 `skill_market_tool` 是否挂载而变：挂载 277，未挂载 289 |
| 23 | skill_market_tool | 288 | `harness/agent/meta_tools/skills/market/skill_market_tool.py` | 从外部源安装/卸载技能（market_backend 存在时 Turn1 挂载）；`skill_search_tool` 的交叉提示经 dynamic_hints 按挂载情况注入：已挂载 288，未挂载 271 |

### 4.4 交互工具（harness 提供，按配置加载）

| # | 工具名 | Token (tiktoken) | 来源文件 | 说明 | 加载条件 |
|---|--------|------------------:|----------|------|----------|
| 26 | ask_question_tool | 316 | `harness/agent/meta_tools/clarification/clarification_agent_tools.py` | 结构化澄清；`requires_confirmation` 驱动危险强调；middleware 强制单轮单次 | server mount policy (interactive web_chat) |
| 27 | **request_answer_user_tool** | **327** (EN) / **512** (ZH) | `harness/agent/meta_tools/answer_user_tool.py` | 搜索 Agent 终局自审门 | 默认关闭（`answer_tool` opt-in，EXTENDED 层） |

### 4.6 子 Agent 委托工具（有子 Agent 配置时加载；空 catalog 零 bind）

| # | 工具名 | Token (tiktoken) | 来源文件 | 说明 |
|---|--------|------------------:|----------|------|
| 28 | delegate_task_tool | 292 + 名册 | `harness/agent/meta_tools/spawn_subagent/delegate_task_tool.py` | 统一委派（mode=single\|batch\|parallel\|council\|alternatives）；绑定时描述 = 固定部分（含 `DELEGATION_TOOL_GUIDANCE`，292）+ catalog 中可用 agent 类型的名册（每个类型一行，随 catalog 变化，不计入 292） |
| 29 | subagent_control_tool | 55 | `harness/agent/meta_tools/spawn_subagent/agent_manage_tool.py` | 运行时控制（action=list\|cancel\|steer\|wait） |
| 30 | send_teammate_message_tool | 32 | `harness/agent/meta_tools/spawn_subagent/send_teammate_tool.py` | Orchestrator 子 Agent P2P 通信 |
| 31 | invoke_acp_agent_tool | 281 | `harness/toolkits/acp/acp_agent_tools.py` | ACP 协议 Agent 委托（有 ACP 配置时） |

### 4.7 浏览器工具（启用浏览器时加载）

| # | 工具名 | Token (tiktoken) | 来源文件 | 说明 |
|---|--------|------------------:|----------|------|
| 37 | browser_navigate_tool | 76 | `harness/toolkits/browser/tools/navigate.py` | 浏览器导航 |
| 38 | browser_snapshot_tool | 111 | `harness/toolkits/browser/tools/snapshot.py` | 页面快照 |
| 39 | browser_interact_tool | 157 | `harness/toolkits/browser/tools/interact.py` | 页面交互 |
| 40 | browser_extract_tool | 111 | `harness/toolkits/browser/tools/extract.py` | 内容提取 |
| 41 | browser_inspect_tool | 65 | `harness/toolkits/browser/tools/inspect.py` | 元素检查 |
| 42 | browser_manage_tool | 131 | `harness/toolkits/browser/tools/manage.py` | 浏览器管理（含 web_vitals 性能洞察） |
| 43 | browser_execute_script_tool | 15 | `harness/toolkits/browser/tools/execute_script.py` | 单轮内以异步 Python 脚本批量执行浏览器动作（Code-as-Action） |
| 44 | browser_ask_human_tool | 96 | `harness/toolkits/browser/tools/takeover.py` | 请求用户临时接管浏览器（2FA/MFA、支付凭据、自动求解器无法处理的验证码等） |

### 4.8 定时任务工具（启用 Cron 时加载）

| # | 工具名 | Token (tiktoken) | 来源文件 | 说明 |
|---|--------|------------------:|----------|------|
| 47 | cron_manage_tool | 1,160 | `harness/toolkits/cron/cron_agent_tools.py` | 定时任务管理；蓝图目录经 `action=blueprints` 按需拉取，不占 Turn1 描述 |

### 4.10 Wiki 知识库工具（有 Wiki 目录时加载）

| # | 工具名 | Token (tiktoken) | 来源文件 | 说明 |
|---|--------|------------------:|----------|------|
| 48 | wiki_query_tool | 79 | `harness/toolkits/wiki/wiki_agent_tools.py` | 查询 Wiki 知识库 |
| 49 | wiki_ingest_tool | 114 | `harness/toolkits/wiki/wiki_agent_tools.py` | 导入内容到 Wiki |
| 50 | wiki_apply_tool | 151 | `harness/toolkits/wiki/wiki_agent_tools.py` | 窄写更新 Wiki 词条（truth/timeline/metadata/create） |

> Wiki 编译/维护由 Settings REST 的 `app/services/wiki/maintain` 承担，不暴露 LLM 工具。

### 4.11 Goal / planning 工具

| # | 工具名 | Token (tiktoken) | 来源文件 | 说明 | 加载条件 |
|---|--------|------------------:|----------|------|----------|
| 56 | complete_goal_tool | 95 | `harness/agent/meta_tools/goals/goal_agent_tools.py` | 显式声明目标完成 | active Goal |
| 57 | todo_write | 203 | `harness/agent/meta_tools/progress/todo_write_tool.py` | 主 Agent 多步进度 | 默认关闭（`planning` / Goal） |

### 4.13 看板工具（启用看板时加载，按角色分组）

**Server bind 策略**：Chat Agent + kanban → `orchestrator` 6 工具；`KanbanTaskRunner` → `worker` 6 工具（两组按角色互斥挂载）。看板/任务 CRUD 走 REST/GUI。解析：`myrm-agent-server/app/ai_agents/general_agent/kanban_tool_mode.py`。

#### Worker 工具（6 个）

| # | 工具名 | Token (tiktoken) | 来源文件 | 说明 |
|---|--------|------------------:|----------|------|
| 58 | kanban_show | 30 | `harness/toolkits/kanban/_worker_tools.py` | 查看当前任务详情（描述/依赖/历史） |
| 59 | kanban_complete | 77 | `harness/toolkits/kanban/_worker_tools.py` | 标记任务完成并提交结构化交接 |
| 60 | kanban_block | 104 | `harness/toolkits/kanban/_worker_tools.py` | 阻塞任务（支持定时自动解除） |
| 61 | kanban_heartbeat | 46 | `harness/toolkits/kanban/_worker_tools.py` | 报告运行中任务的进度（SSE） |
| 62 | kanban_comment | 75 | `harness/toolkits/kanban/_worker_tools.py` | 跨任务评论协调（不限所有权，Worker 可评论任意任务） |
| 63 | kanban_attach | 74 | `harness/toolkits/kanban/_worker_tools.py` | 挂接沙箱文件或 HTTPS URL 到任务 |

#### Orchestrator 工具（6 个）

| # | 工具名 | Token (tiktoken) | 来源文件 | 说明 |
|---|--------|------------------:|----------|------|
| 64 | kanban_add_task | 250 | `harness/toolkits/kanban/_orchestrator_tools.py` | 添加新任务（depends_on/优先级/技能/幂等） |
| 65 | kanban_list_tasks | 122 | `harness/toolkits/kanban/_orchestrator_tools.py` | 列出任务；可选 `include_stats`；`task_id` 单查 |
| 66 | kanban_unblock | 111 | `harness/toolkits/kanban/_orchestrator_tools.py` | 解除 BLOCKED 任务 |
| 67 | kanban_cancel_task | 75 | `harness/toolkits/kanban/_orchestrator_tools.py` | 取消任务（移入 ARCHIVED；运行中任务同时停止 worker） |
| 68 | kanban_retry_task | 75 | `harness/toolkits/kanban/_orchestrator_tools.py` | 重试 FAILED 任务（重置为 READY 并清除失败计数；可选更新描述） |
| 69 | kanban_revise_plan | 141 | `harness/toolkits/kanban/_orchestrator_tools.py` | 原子修订看板 DAG 计划（增/改/归档任务并调整依赖边） |

### 4.17 桌面语义控制工具（启用 Computer Use 时加载）

`create_desktop_tools()` 定义 3 个工具（`harness/toolkits/computer_use/desktop_agent_tools.py:72/150/204`）：

| # | 工具名 | Token (tiktoken) | 来源文件 | 说明 |
|---|--------|------------------:|----------|------|
| 77 | desktop_snapshot_tool | 91 | `harness/toolkits/computer_use/desktop_agent_tools.py` | AX 树 + @dref，可选截图 |
| 78 | desktop_interact_tool | 40 | `harness/toolkits/computer_use/desktop_agent_tools.py` | @dref 语义交互（含 set_value） |
| 79 | desktop_vision_tool | 69 | `harness/toolkits/computer_use/desktop_agent_tools.py` | 显式截图/坐标回退 |

### 4.18 内部分类（非 LLM 工具，默认 GeneralAgent Turn1 = 0 token）

编排信号**不是 LLM 工具**，不在 `_TOOL_LAYERS`。SSOT：`agent/orchestration/`。LLM 工具清单见 `TOOL_MANAGEMENT_SYSTEM.md` 自动生成表。

| 桶 | 成员 | 说明 |
|----|------|------|
| Orchestration signal | `submit_verdict` | Verifier 子 Agent 会话 |

PTC（`myrm_tools.spawn_subagent` / `notify`）等非 LLM 实现见 §4.25，零 Turn1 bind。

Token 明细（tiktoken o200k_base）：

| # | 名称 | Token (tiktoken) | 来源 |
|---|------|------------------:|------|
| 86 | submit_verdict | 26 | `orchestration/signals/verifier.py` |

### 4.24 Server 层业务工具（server 启动时动态注册，依赖第三方 SDK）

| # | 工具名 | Token (tiktoken) | 来源文件 | 说明 | 加载条件 |
|---|--------|------------------:|----------|------|----------|
| 88 | channel_notify_tool | 102 | `server/services/agent/outbound_notify/channel_notify_tool.py` | Agent 主动 IM 出站（白名单+频控+附件） | Agent 配置 `notify_targets` 时 [Turn1] |
| 89 | image_tool | 144 | `server/ai_agents/media_tools/image_agent_tool.py` | 图像生成工具（DALL-E / SD / Flux）；描述含运行期模型名，144 为引擎默认模型 dall-e-3 | enabled_builtin_tools: image_generation |
| 90 | video_tool | 159 | `server/ai_agents/media_tools/video_agent_tool.py` | 视频生成工具；描述含运行期供应商与模型名，159 为引擎默认配置 openai/sora | enabled_builtin_tools: video_generation |
| 91 | tts_generate | 43 | `server/ai_agents/media_tools/tts_agent_tool.py` | 语音合成工具 | enabled_builtin_tools: tts |
| 92 | artifact_publish | 78 | `server/services/hosting/agent_publish_tool.py` | 工件/网页在线打包与托管发布 | server 凭证就绪 |

> 注：`x-live-search` 采用 Prebuilt Skill + 沙箱标准脚本 PTC（Programmatic Tool Calling）范式，0 Action Tool 注册（Turn1 0 Token 开销，不污染 Action Space）。

### 4.25 PTC 桥接（非 LLM 工具，非 `_TOOL_LAYERS` 登记）

| 名称 | 暴露形式 | 说明 |
|------|----------|------|
| `spawn_subagent` | `myrm_tools.spawn_subagent()` | PTC 脚本内阻塞 spawn；≠ LLM `delegate_task_tool` |
| `notify` | `myrm_tools.notify()` | Workflow 阶段 SSE；0 Turn1 bind |

---

## 五、动态注入内容（~1,200 tokens，Turn 1 典型值）

| 组件 | Token (估算) | 来源 | 说明 |
|------|------------:|------|------|
| user_instructions | ~200 | `server/ai_agents/agent_middlewares/user_instructions_middleware.py` | 用户自定义指令（SystemMessage，注入在 system prompt 之后） |
| Memory context | ~500 | `harness/agent/middlewares/memory_context/memory_context_middleware.py` | `<user_memory_context>` **SystemMessage**，只含用户存储的记忆；已学习的事实不进块（检索走 `memory_search_tool`） |
| Inline skills 列表 | ~500 | 技能系统 | `<skills>` 块内联展示可用技能名+描述（取决于已安装技能数量） |

**缓存特性**：
- `user_instructions` 同用户同会话内稳定，不破坏缓存
- `Memory context` 同用户连续对话内稳定；已学习的事实不进块（由 tool 检索）
- `Inline skills` 同用户同技能配置内稳定

---

## 六、格式开销（~2,900 + 参数 schema ~5,519 ≈ **~8,419 tokens**，模型/API 相关）

| 组件 | Token (估算) | 说明 |
|------|------------:|------|
| 工具参数 schema | ~368/tool | 参数 JSON Schema 本体；`estimate_bound_tools_tokens` 不含此项，仅 `measure_tool_schema_tokens.py` 全量口径统计 |
| schema wrapper 包装 | ~65/tool | 每个工具 API 格式的**包装**开销（function name、schema 外壳等），**不含参数 schema**；参数 schema 见上一行 |
| Qwen tokenizer 差异 | ~20-30% | Qwen3 tokenizer 对中文分词效率低于 tiktoken，中文内容 token 数会更高 |
| 特殊 token/消息格式 | ~500 | role tags, tool_use markers, message boundaries 等 |

---

## 七、Fast 模式 Turn1（`action_mode='fast'`）

> SSOT：`myrm-agent-server/app/services/agent/params/converter.py` · `params/_ARCH.md`

| 子模式 | Turn1 eager 工具 | 说明 |
|--------|------------------|------|
| normal | web_search + web_fetch + request_answer_user（不挂载记忆工具） | max_tool_calls=8 |
| deep | 同上 + SufficiencyConfig 增强搜索 | prompt 追加 `<deep_search_mode>`（web_fetch 深读 + answer 自审）；max_tool_calls=20 |

**不含**：file/bash/glob/grep、memory 工具（记忆只经 `<user_memory_context>` 注入，`RecallMode.CONTEXT`）、browser（browser 仅 Agent profile `browser` 开关 opt-in）、kanban、wiki、planning、子 Agent 委托。

---

## 八、用户消息

| 组件 | Token | 说明 |
|------|------:|------|
| 用户第一条消息 | ~20 | 典型短消息如 "用Python写一个快速排序函数" |
| `<current_datetime>` 标签 | ~12 | 注入到最后一条 HumanMessage 中的当前时间戳 |

---

## 总计估算

### 典型 Turn 1 场景（默认智能体，记忆+搜索+技能；无 answer/todo/工作台）

| 分类 | Token (tiktoken) | 明细 |
|------|------------------:|------|
| System Prompt 层 | **1,861** | `messages[0]` 1,161（ZH · full，跨用户缓存）+ widget 能力声明 348 + 跟随用户输入的 canary ≈53 与安全边界 299 |
| CORE 工具层 | **2,599** | 8 工具描述（含 bash_process；`measure_turn1_token_inventory.py` 实测，o200k_base） |
| HIGH_PRIORITY 工具层 | **2,445** | web_search + memory×3 + skill_select |
| EXTENDED 工具层 | **0** | 默认 profile 无附加（opt-in 按需挂载） |
| schema wrapper 包装 | **845** | 13 工具 × 65（仅 API 包装，不含参数 schema） |
| 动态注入 | ~1,200 | user_instructions + memory_context + inline_skills |
| 消息格式 | ~500 | role tags, boundaries 等 |
| 用户消息 | ~32 | 短消息 + datetime 标签 |
| **tiktoken 小计** | **~9,480** | |

### 最小 Turn 1 场景（仅 CORE 8 工具，无 HIGH_PRIORITY/EXTENDED）

| 分类 | Token (tiktoken) |
|------|------------------:|
| System Prompt 层 | **1,861** |
| CORE 工具层 | **2,599** |
| schema wrapper 包装 | **520** (8 工具 × 65) |
| 用户消息 | ~32 |
| 消息格式 | ~300 |
| **tiktoken 小计** | **~5,310** |

### 满载场景（全部已登记 LLM 工具同轮 bind：浏览器+Cron+Wiki+子Agent+看板+桌面控制+IM 通知+媒体生成+发布）

| 分类 | Token (tiktoken) |
|------|------------------:|
| System Prompt 层 | **1,861** |
| CORE 工具层 | **2,599** |
| HIGH_PRIORITY 工具层 | **2,445** |
| EXTENDED + EXTERNAL（38 + 5 = 43 工具） | ~6,601（**粗估**：§四 各行描述值求和，EXTENDED 38 个 ~6,075 + EXTERNAL 5 个 ~526；`measure_turn1_token_inventory.py` 只构建 Turn-1 默认的 13 个工具，这两层不由它计量） |
| schema wrapper 包装 | **3,640** (56 工具 × 65) |
| 动态注入 | ~1,200 |
| 消息格式 | ~500 |
| **tiktoken 小计** | **~18,850（粗估）** |

> 工具数量以文件末尾 `TOOL_COUNT_BEGIN/END` 自动生成块为 SSOT（当前 56 LLM 工具 = CORE 8 + HIGH_PRIORITY 5 + EXTENDED 38 + EXTERNAL 5）。本场景假设全部 56 工具同轮 bind，EXTENDED / EXTERNAL 行为 §四 各行描述值求和，仅作量级参考：`delegate_task_tool` 只计固定部分，不含运行期名册；kanban 的 worker 与 orchestrator 两组工具按角色互斥挂载，此处同时计入；`image_tool` / `video_tool` 的描述含运行期模型名，按引擎默认配置计。

---

## 缓存分层效果

```
[CORE: web_fetch + bash + file_* + glob + grep (~2,599 tok, 8 tools)]
  ↑ 通用 Agent 基线前缀（agent 模式）

[HIGH_PRIORITY: web_search + memory_* + skill_select (~2,445 tok)]
  ↑ web_search 优先；memory 组紧随；skill_select 承接；GUI 可关

[EXTENDED: 可选工具 (~0~6,075+ tok)]
  ↑ 按需变化，不影响 CORE/HIGH_PRIORITY 前缀

[System Prompt: messages[0] 1,161 (ZH·full)]
  ↑ 冻结，跨用户共享缓存

[widget 能力声明 348]
  ↑ 紧随前导 system 消息，字节恒定（仅 web_chat 的 prompt_mode=full 注入）

[跟随用户输入: canary ≈53 + 安全边界 299]
  ↑ 位于最新用户消息之后，不进入共享前缀

[Dynamic: user_instructions(~200) + memory_context(~500) + skills(~500)]
  ↑ 同用户会话内稳定
```

**实测 Turn1 工具层合计**：描述 **5,044** + schema wrapper **845** = **5,889 tokens**（13 工具，`measure_turn1_token_inventory.py`，o200k_base，macOS arm64 宿主，bash OS hint 57）。宿主无关口径下 bash 计入静态描述 1,355，为 **5,832**——CI 门禁以该口径判定，见下方门禁表。

> **口径边界（重要）**：`5,889` 为「描述 + wrapper 包装」口径，**不含工具参数 schema**。参数 schema 是真实发送给模型的 payload 一部分，全量口径见 `measure_tool_schema_tokens.py`（其 `Turn-1 Total Budget` = 描述 **5,044** + 参数 schema + wrapper **845**）。下方各 Turn-1 场景表的「schema wrapper 包装」行与 harness 门禁阈值均沿用「描述 + wrapper」口径，与 `estimate_bound_tools_tokens`（`utils/token_estimation.py:117-120`）一致；该估算仅用于展示与预检，压缩与预算决策以 provider 实测 `prompt_tokens` 为准（`estimate_context_tokens` 取 `max(estimate, provider)`）。

**CI 门禁（横跨 harness / server 两仓）**：

| 仓 | 门禁文件 | 锁定项 |
|----|----------|--------|
| harness | `tests/architecture/test_prompt_token_budget_gate.py` | Turn-1 默认工具集 ≤ **6,500**（宿主无关口径当前 **5,832**，余量 668：bash 计入静态 1,355、不计宿主 OS hint；live hint 另锁 ≤ 180（OS 与 toolchain 约 100，沙箱的 VNC 行 57）。口径=描述+wrapper，**不含参数 schema**）；`AGENT_CORE_RULES` ≤ 301（实测 286 + 5%）/ `SECURITY_BOUNDARY_SYSTEM_RULES` ≤ 314（实测 299 + 5%）/ `DATETIME_SYSTEM_RULES` ≤ 120；SystemMessage 哈希跨调用恒定 |
| harness | `tests/scripts/test_measure_turn1_token_inventory.py` | 逐工具描述 token 与 §二/§三 表格一致（漂移即失败并指出工具名）；`bash_code_execute` 的宿主相关 OS hint 单独扣减，上限判定同样以静态 1,355 计，故 macOS 与 Linux CI 结果一致 |
| server | `tests/ai_agents/test_prompt_integrity.py:152-175`（`cl100k_base`，仅英文 CORE） | CORE full ≤ **2,000** |
| server | `tests/architecture/test_first_turn_static_prompt_budget.py`（`o200k_base`） | 静态首轮 system 消息（CORE + 时间规则 + 核心行为规则 + web_chat 渠道提示（为空），所有模型相同）按面与 zh-CN / en 封顶，上限 = 实测 +5%（通用 full：zh-CN **1,217**（实测 1,159）/ en **1,022**（实测 973）；快速搜索：zh-CN **2,316**（实测 2,205）/ en **1,570**（实测 1,495）；深度搜索：zh-CN **2,453**（实测 2,336）/ en **1,688**（实测 1,607））；`<widget_capability>` ≤ **366**（实测 348）。与上表 `messages[0]` 同一组分量，按拼接后的整段计数，与分量求和相差几个 token |


---

## 工具层级注册表 (tool_layers.py)

<!-- TOOL_COUNT_BEGIN -->
LLM tools: **56** (Harness 51: CORE 8 + HIGH_PRIORITY 5 + EXTENDED 38; External 5: server vendor). Orchestration signals: **1**. PTC runtime tools: **6** (`human_ask`, `llm_query`, `llm_query_batched`, `notify`, `spawn_subagent`, `steer_child`). LLM-tool SSOT: `tool_layers.py` + `_tool_layer_bootstrap.py`. PTC SSOT: `agent/dynamic_workflow/tools/` + `PTC_RUNTIME_TOOL_NAMES`. Orchestration SSOT: `agent/orchestration/`. Auto-generated by `scripts/validate_tool_registry.py --generate-docs`.
<!-- TOOL_COUNT_END -->
未注册的工具（如 MCP 动态工具）自动归入 EXTENDED，并在运行时打印 WARNING 日志。
完整列表请直接查看 `tool_layers.py`。
