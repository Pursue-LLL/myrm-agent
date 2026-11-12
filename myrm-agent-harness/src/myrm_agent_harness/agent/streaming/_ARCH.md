# Streaming Execution & Recovery Architecture

## 架构概述

提供流式事件转换与分发、思考标签脱毒、重复循环熔断、高频事件压实、Last-Event-ID 重连重放缓冲，以及流式错误的重试与恢复能力。详细设计见 [STREAMING_SYSTEM.md](STREAMING_SYSTEM.md)。

## 文件清单

| 文件 | 地位 | 职责 |
| --- | --- | --- |
| `__init__.py` | 入口 | 包入口（不再导出符号，调用方按模块路径导入） |
| `agent_core_rules.py` | 核心 | 核心行为规则（所有模型共用，与模型名无关）：反叙述、工具结果诚实、断言缺失前先验证、主动检索求证、仅原生 Function Calling（禁输出 XML 工具调用）、调用工具前先查已有上下文 |
| `answer_draft.py` | 核心 | 流式回复文本累积器 `AnswerDraft` 与重启契约判定 `is_answer_restart`：恢复重放时只丢弃“最近一次 `tool_start` 之后”的在途段落（已完成的工具步骤由检查点保留，模型从其后续写，之前的文本不会重发）；所有从 `process_stream` 事件拼最终回复的消费者统一使用，禁止各自重写该规则 |
| `artifact_events.py` | 核心 | 工件事件处理（文件工件、UI工件、内联图片工件与实时内容更新） |
| `channel_output_hints.py` | 核心 | 交付渠道输出格式提示词生成（Channel-Aware Output Guidance）与前置提示保障 |
| `citation_audit.py` | 核心 | 流式回复引用标记审计（【N】序号与信息源对照验证） |
| `event_handlers.py` | 核心 | LangGraph updates/messages 流式事件向业务事件转换与图片事件分发。错误事件经 `_error_category_value` 归一化 `ToolErrorCategory`：**必须取 `.value`**（该枚举是裸 `str` mixin，`str()` 会渲染成 `'ToolErrorCategory.ESTOP'`），否则 SSE 契约泄漏 Python 类路径、且 `classify_tool_fault_side` 因表内是值形字符串而全部失配退化为 `unknown`。只记录“被扣留工具调用”的 AIMessage（无 content、无 `tool_calls`，但 `additional_kwargs["tool_call_recovery"]` 含 `safe=False`）必须保留在 `collected_messages`：LangGraph 以末条无 `tool_calls` 的 AIMessage 结束整轮，若按“空消息”丢弃，恢复处理器就看不到这次失败的工具调用，整轮静默结束。真正的空回复（无 content、无推理文本、无工具调用）不进 `collected_messages`（没有可重发的内容），恢复处理器改读 `latest_reply.latest_model_reply` 记下的本轮最后一次回复。工具错误步骤的 `error` 经 `core.security.model_directed_notes.user_facing_text` 截到第一条给模型的备注之前（`[System: …]`、`[SECURITY_DENIAL_DIAGNOSTIC]`），界面只显示拒绝的原因，模型读到的 ToolMessage 原文不变；整段都是备注时回退为 `Unknown error`。成功的工具结果只从 `ToolMessage.additional_kwargs[TOOL_SOURCES_KWARG]` 读取引用来源（由 `middlewares/tooling/tool_sources_hoisting.py` 在拦截的最后一步从 `{content, metadata}` 结果取出），交给本次运行的 `SourceTracker`，产出 `reviewing_sources` 步骤与 `sources` 事件；不解析 `content` 文本 |
| `interrupt_events.py` | 核心 | LangGraph `__interrupt__` 分片 → 流事件：每个中断一个事件，顶层带卡片 id `interruptId`（即该中断的 LangGraph id，每次挂起各有一个；并行子 agent 各自挂起时，每张审批卡片可单独作答；resume 侧见 `_internals/resume_addressing.py`） |
| `latest_reply.py` | 核心 | `latest_model_reply(update)`：一次 `updates` 分片携带的最后一条 AIMessage，包括 `collected_messages` 不收的空回复；由 `StreamDispatcherMixin` 记为 `_latest_reply`，供截断/空回复恢复处理器判断「本轮最后一次回复」 |
| `message_builder.py` | 核心 | 原始用户输入向 LangChain 消息结构转换与时间戳就地注入 |
| `reasoning_scrubber.py` | 核心 | 模型思考推理标签（`<think>`等）状态机清洗与独立事件重定向 |
| `repetition_scrubber.py` | 核心 | 模型退化重复循环实时检测与流式熔断保护 |
| `run_digest.py` | 核心 | 智能体实时执行快照 DTO 与步骤信息归纳聚合器 |
| `source_numbering.py` | 核心 | 续号：`restore_source_numbering(tracker, checkpointer, run_config)` 在一次运行开跑时读线程检查点里 ToolMessage 的 `additional_kwargs["sources"]`（`tool_interceptor_middleware` 在这些条目里盖了模型读到的来源编号），交给 `SourceTracker.restore`，使同一线程里的审批续跑与后续轮次接着已发过的编号往下编，一个编号始终指同一个来源；没有检查点器、没有线程 id 或线程里还没存过来源时从 1 起编，检查点读取失败时（`read_checkpoint_messages` 记 WARNING）这次运行同样从 1 起编，运行本身照常进行 |
| `source_tracker.py` | 核心 | 单次运行的引用信息源追踪：带 url 的来源按 `url_dedup_key` 去重（同一页面的不同拼写算一个来源，不同锚点算不同来源），编号、增量分发。工具要在结果文本里给来源编号时，用 `StreamExecutor.execute` 开跑时绑进 `source_indexer_var` 的 `index_for` 取号（早于卡片发出），卡片的 `index` 沿用同一个编号；工具改写过 URL（`redirect_url` 存原链接）的卡片按原链接认号，两个编号落到同一最终链接时，后到的卡片保留原链接，以免被下游按 URL 合并；`restore()` 用同一线程此前盖章的来源接上编号（新编号接在已发过的最大编号之后，盖过章的来源各自认回原编号（同一页面的几种拼写可以带同一个编号），恢复本身不发卡片） |
| `step_builder.py` | 核心 | 智能体步骤执行数据格式化（面向 WebUI 的多类型工具状态渲染契约） |
| `stream_buffer.py` | 核心 | 内存滑动窗口流式重放缓冲与 Last-Event-ID 重连恢复。一个缓冲只属于一次运行，结束后只重放、不再接收新事件；订阅者闲置满 `HEARTBEAT_INTERVAL_SEC`（15 秒）就收到 `HEARTBEAT_FRAME`（`event: heartbeat`、空体的协议保活帧），两者作为常量导出，server 的 attach 流用同一帧同一间隔，页面据此判连接存活；`GlobalStreamRegistry.get_or_create` 把某个 id 现有的缓冲交给重连的客户端，`start_run` 给新一次运行换一个新缓冲（审批通过后的续跑沿用被停下那一轮的 message id，若拿到它已结束的缓冲，客户端收到的是那一轮的重放而不是续跑），被换下的缓冲留给还在读它的人读完；`remove(run_id, buffer)` 带缓冲时只清掉仍登记的那一个，换下的缓冲排定的延时清理不会误结束新一次运行的流 |
| `stream_compactor.py` | 核心 | 高频文本片段流式合并压实器（降低前端事件风暴与渲染开销） |
| `stream_dispatcher.py` | 核心 | 流式执行引擎事件分发 Mixin（覆盖 Tool Stdout、UI 更新、任务步骤、AgentStatus 状态机透传（含 `restart`：丢弃正在流出的草稿）与 `__interrupt__` 分片分发——中断转事件见 `interrupt_events.py`；并把每个 `updates` 分片里的最后一条 AIMessage 记为 `_latest_reply`，见 `latest_reply.py`） |
| `stream_executor.py` | 核心 | 流式执行引擎生命周期封装（Agent.astream 调度、重试恢复与异常拦截；被 Stop 打断的模型请求以 `OperationCancelledError` 早退，与循环内 Stop 同一收尾；开跑时把本次运行追踪器的 `index_for` 绑进 `source_indexer_var`，工具给来源编号时用，并经 `source_numbering.restore_source_numbering` 读线程检查点，让编号接着同一线程此前发过的往下编） |
| `stream_fatal_error.py` | 核心 | 致命错误上报 Mixin：把一次运行的异常转成带诊断的 GUI 错误事件（故障归属、恢复建议、冷却剩余时间）、以脱敏文本记入运行统计（`AgentRunStatistics.record_error`，随 SESSION_END 钩子载荷离开进程）、写入事件日志并抛出 `MyrmLLMError`；`StreamExecutor` 经多继承使用 |
| `types.py` | 核心 | 流式事件类型定义与 core.events.types 兼容重导出 |
| `utils.py` | 辅助 | 时间戳规则、时区管理上下文变量及工具名称规范化等通用辅助函数 |
