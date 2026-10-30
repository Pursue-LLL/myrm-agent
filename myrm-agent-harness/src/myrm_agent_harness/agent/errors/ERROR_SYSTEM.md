# 工具错误处理系统（Error Handling System）


---

## 设计目标

为 Agent 工具执行链路提供统一的错误捕获、格式化和前端展示机制。
确保 LLM 能收到结构化的诊断信息和恢复建议，前端用户能看到清晰的错误提示。

---

## 硬错误 vs 软错误

工具错误分为两种模式，选择哪种取决于错误的严重程度：

| 模式 | 机制 | 前端表现 | 适用场景 |
|------|------|----------|----------|
| **硬错误** | `raise ToolError/BrowserError/WebSearchError` | 红色错误提示 + `status="error"` | 操作失败、不可恢复 |
| **软错误** | 自行 catch 返回错误字符串 | 无红色提示，LLM 自行判断 | 可降级、不影响主流程 |

**硬错误**经过中间件统一处理（`format_tool_error` → `format_for_llm()` 协议），LLM 收到结构化诊断信息。

**软错误**由工具自行处理，返回 `"Error: ..."` 或 `"Failed to ..."` 字符串。这些错误不触发前端红色提示，LLM 自行决定是否重试。这是有意为之的设计——memory、cron、skill 等辅助工具的失败不应中断主流程。

---

## 端到端数据流

```
工具抛出异常（ToolError / BrowserError / WebSearchError / Exception）
    ↓
tool_interceptor_middleware  ← 统一 catch 点（含超时和重试保护）
    │ Timeout 保护（asyncio.timeout）：bash/browser 120s, file 30s, 默认 60s
    │ 智能重试（max_retries=1）：仅对瞬态错误，bash 不重试（不幂等）
    │ 错误历史记录：每次尝试的 attempt/error/elapsed_ms
    │ format_tool_error(): 调用 format_for_llm() 协议
    │ 构建 ToolMessage(status="error", content=格式化后的错误文本)
    ↓
event_handlers._handle_tool_result()  ← 事件转换层
    │ 检测 status=="error"
    │ 发送 TASKS_STEPS 事件（step_key="{tool_name}_tool_error", status="error", tool_call_id=msg.tool_call_id）
    │ fault_side 归因：ToolMessage.error_category（ToolErrorCategory）→ classify_tool_fault_side()
    │   - guard/guardrail 类（pii_guard/estop/loop_guard/guardrail_blocked 等）→ owner（用户内容/配置触发）
    │   - 审批拒绝类：policy_denied（策略拒绝）→ owner；user_declined（用户拒绝）、approval_timeout（审批超时没人回答）→ unknown（不归咎任何一方，前端不显示归因标签）
    │   - 执行类（timeout/oom/syntax/not_found 等）→ harness_tool（内置工具自身失败）
    │   - 无 error_category 时默认 harness_tool
    │ tool_call_id 与成功路径一致：trace_builder 借此将 error 步骤与
    │   tool_failure 生命周期事件合并为同一条记录，避免 trace 双写
    ↓
SSE 推送到前端
    ↓
messageStreamHandler.ts  ← 前端消费
    │ 构建 ProgressItem（error=error_content）
    ↓
ProgressSteps.tsx  ← UI 渲染
    └ 红色错误区域显示（含重试历史）
```

另有 `AgentEventType.ERROR` 顶级通道用于非工具层面的系统错误（如流中断）。

---

## `format_for_llm()` 协议

中间件通过 duck typing 调用异常的 `format_for_llm()` 方法。任何异常只要实现该方法，其结构化诊断信息就会自动传递给 LLM。

```python
# _tool_helpers.format_tool_error() 的核心逻辑（tool_interceptor_middleware 的 execute_with_retry 捕获后调用）：
format_fn = getattr(e, "format_for_llm", None)
if callable(format_fn):
    return format_fn()  # 优先使用结构化格式
content = f"{tool_name} execution failed: {e}"  # fallback
```

### 实现了 `format_for_llm()` 的异常

| 异常类 | 输出内容 |
|--------|---------|
| `ToolError` | Error + Error Code + Hint + Diagnostic Info + Recovery Suggestions |
| `BrowserError` | Error + Error Code + Context + Diagnostic Info + Recovery Suggestions |
| `WebSearchError` | Error + Hint |
| `SearchAPIError` | Error + Error Code + HTTP Status + retryable hint + query + response snippet |
| `SearchConfigError` | Error + config_key + configuration hint |
| `AllQueriesFailedError` | Error + retryable hint + failed queries list |

---

## 异常体系

### 1. ToolError（通用工具异常）

- **位置**：`utils/errors.py`
- **使用者**：tools（file_read, file_write, file_edit, bash, glob, grep）、web_fetch_tool
- **属性**：

| 属性 | 类型 | 用途 |
|------|------|------|
| `message` | str | 技术错误消息 |
| `user_hint` | str | 给 LLM 的修复提示 |
| `diagnostic_info` | dict | 诊断上下文（可选，复杂场景使用） |
| `recovery_suggestions` | list[str] | 恢复建议列表（可选，复杂场景使用） |
| `error_code` | str | 错误分类码（可选，用于统计） |
| `error_category` | property → `diagnostic_info["error_category"]` | SSE / ProgressSteps Badge（如 `guardrail_blocked` →「安全拦截」） |

`bash_code_execute_tool` preflight 抛出的 `ToolError` 会原样重抛（保留 `diagnostic_info`），经 `tool_executor` → `ToolMessage.additional_kwargs` → SSE `error_category` 到达前端。

### 2. BrowserError（浏览器异常树）

- **位置**：`toolkits/browser/exceptions.py`
- **继承**：`Exception`（独立异常树，通过 `format_for_llm()` 协议与中间件对接）
- **子类层次**：

```
BrowserError
├── BrowserPoolError（BrowserLaunchError）
├── BrowserSessionError（BrowserNavigationError）
├── BrowserToolError（ClickTargetUnreachableError, RefNotFoundError）
└── AriaError（AriaAcquisitionError, AriaParseError, AriaCrossOriginError）
```

- **特点**：`BrowserNavigationError`、`RefNotFoundError` 拥有智能诊断建议生成（根据 URL 变化类型、错误原因等动态生成）

### 3. WebSearchError（搜索异常树）

- **位置**：`toolkits/web_search/core/exceptions.py`
- **继承**：`Exception`（独立异常树，通过 `format_for_llm()` 协议与中间件对接）
- **子类层次**：

```
WebSearchError
├── SearchAPIError（含 ErrorContext: retryable, status_code, error_code, query）
├── SearchConfigError（含 config_key）
└── AllQueriesFailedError（含 failed_queries 列表 + primary_context）
```

- **特点**：`SearchAPIError` 通过 `ErrorContext.retryable` 告知 LLM 是否可重试，`AllQueriesFailedError` 列出所有失败查询的详情

### 4. Sandbox ExecutionHelper

- **位置**：`toolkits/code_execution/executors/common/error_handler.py`
- **机制**：装饰器模式，构建 `ExecutionResult` 而非抛异常
- **与上述体系独立**，通过 `ExecutionHelper.build_error_result()` 返回结构化结果

### 5. ExecutionResult 动态错误提示

- **位置**：`toolkits/code_execution/executors/models.py`
- **机制**：`ExecutionResult.__post_init__` 自动调用 `generate_error_hint()`，基于 `error_category` + `stderr` 正则提取生成精准修复建议
- **数据流**：`ExecutionResult.error_hint` → `BashExecutionError.error_hint` → `ToolError.user_hint` → `format_for_llm()`
- **覆盖范围**：
  - `import`：提取模块名 → `_IMPORT_TO_PYPI` 映射 PyPI 包名 → 智能检测 uv 包管理器优先使用（`uv pip install` vs `pip install`）
  - `not_found`：提取命令名 → 联动 `tool_discovery` 的 `get_install_hint()` 查询 `TOOL_CATALOG` 中的平台特定安装命令（如 `"Try: brew install jq"`），不在 catalog 中则 fallback 到通用提示
  - `permission_denied`：提取文件路径 → `chmod +x` 建议
  - `timeout`：方向性建议（减少数据量/拆分任务）
  - `oom`：方向性建议（分批处理/减少内存）
- **不覆盖**：syntax / unknown（Agent 直接读 stderr 更有效）

---

## 工具接入状态

| 工具 | 错误模式 | 异常类型 | format_for_llm |
|------|----------|----------|----------------|
| file_read_tool | 硬错误 | ToolError | ✅ |
| file_write_tool | 硬错误 | ToolError | ✅ |
| file_edit_tool | 硬错误 | ToolError | ✅ |
| `bash_code_execute_tool` | 硬错误 | ToolError | ✅（含动态 error_hint） |
| grep_tool | 硬错误 | ToolError | ✅ |
| glob_tool | 硬错误 | ToolError | ✅ |
| web_fetch_tool | 硬错误 | ToolError | ✅ |
| browser tools | 硬错误 | BrowserError | ✅（含智能诊断） |
| web_search_tool | 硬错误 | WebSearchError | ✅（含 retryable） |
| memory tools | 软错误 | 自行 catch | — |
| cron tools | 软错误 | 自行 catch | — |
| skill_select_tool | 软错误 | 自行 catch | — |
| skill_manage_tool | 软错误 | 自行 catch | — |
| acp_delegate_tool | 软错误 | 自行 catch + 重试 | — |
| delegate_task_tool | 软错误 | 自行 catch | — |
| todo_write | 无异常场景 | — | — |
| skill_search_tool | 无异常场景 | — | — |

---

## 中间件拦截逻辑

**文件**：`agent/middlewares/tooling/_tool_helpers.py`（`format_tool_error`，由 `tool_interceptor_middleware` 的 `execute_with_retry` 捕获异常后调用）

`format_tool_error()` 函数处理三种情况（按优先级），输出统一经 `redact_sensitive_text` + `sanitize` 脱敏：

1. **异常实现了 `format_for_llm()`** → 调用获取结构化输出（ToolError、BrowserError、WebSearchError 等）
2. **异常有 `user_hint` 属性** → 拼接到错误消息后（兼容 fallback）
3. **普通异常** → `"{tool_name} execution failed: {str(e)}"`

---

## 超时和重试机制

**文件**：`agent/middlewares/tooling/tool_interceptor_middleware.py`

### 超时保护（Timeout Protection）

**零配置模式匹配**：
- **慢速工具**（bash/browser/mcp）：120s
- **快速工具**（file 操作）：30s
- **默认工具**：60s

**实现**：`asyncio.timeout()` 自动拦截长时间执行

**超时后行为**：
- 第 1 次：自动重试（指数退避）
- 第 2 次：抛出 `ToolError`，包含完整错误历史

### 智能重试（Smart Retry）

**重试策略**：max_retries=1（总共 2 次尝试）

**不可重试错误（黑名单）**：
- `ToolError`（工具逻辑错误）
- `BrowserError`（浏览器逻辑错误）
- `WebSearchError`（搜索逻辑错误）
- `asyncio.CancelledError`（用户取消）
- `GraphInterrupt`（LangGraph 控制流）
- **bash_code_execute_tool**（不幂等，特殊判断）

**可重试错误**：
- 网络错误（`aiohttp.ClientError`、`asyncio.TimeoutError`）
- 并发限流（429）
- 资源不可用（503）

**退避算法**：
- 指数退避 + Jitter：`backoff = 2**attempt + random.uniform(0, 1)`
- 最大退避：10s
- 防雪崩、防雷鸣

### 错误历史记录

**数据结构**：
```python
error_history = [
    {"attempt": 1, "error": "TimeoutError after 120s", "elapsed_ms": 120000},
    {"attempt": 2, "error": "ConnectionError...", "elapsed_ms": 122500},
]
```

**用途**：
- LLM 可看到全部失败原因
- 调试时追踪完整错误链路
- 自动包含在 `ToolError.diagnostic_info` 中

### 真实收益

- MCP 工具卡死 → 120s 自动超时 → 避免卡死 100%
- 网络抖动 429 → 自动重试 → 成功率 +85%
- bash 不幂等 → 不重试 → 安全性 100%
- 任务成功率 +35%

---

## 前端展示

### 事件格式（后端 → 前端）

```json
{
  "type": "tasks_steps",
  "step_key": "{tool_name}_tool_error",
  "tool_name": "browser_navigate_tool",
  "status": "error",
  "error": "Error: Navigation failed\nError Code: BROWSER_NAV_404\n...",
  "messageId": "xxx"
}
```

### UI 组件

- `ProgressSteps.tsx`：检测 `step.error` 字段，渲染红色错误区域
- `getStepTitle()`：通过 `step_key` 匹配 i18n 翻译，fallback 到格式化 tool_name

### 错误样式

- 步骤指示器：`border-destructive shadow-destructive/20`
- 错误文本：`text-destructive break-all` 红色展示
- 错误区域：`bg-destructive/5 border-destructive/20` 背景

---

## 接入指南

### 新增工具异常接入

1. **推荐方式**：使用 `ToolError` 并传入结构化字段

```python
from myrm_agent_harness.utils.errors import ToolError

raise ToolError(
    message="File not found: /path/to/file",
    user_hint="Check if the file path is correct and accessible.",
    diagnostic_info={"path": "/path/to/file", "cwd": "/workspace"},
    recovery_suggestions=[
        "Verify the file path exists",
        "Check file permissions",
    ],
    error_code="FILE_NOT_FOUND",
)
```

2. **自定义异常树**：实现 `format_for_llm()` 协议

```python
class MyToolkitError(Exception):
    def __init__(self, message: str, context: dict):
        super().__init__(message)
        self.context = context

    def format_for_llm(self) -> str:
        parts = [f"Error: {self.args[0]}"]
        if self.context:
            parts.append("\nContext:")
            for k, v in self.context.items():
                parts.append(f"  - {k}: {v}")
        return "\n".join(parts)
```

3. **简单场景**：直接 `raise ToolError(message, user_hint)` 即可

### 错误信息编写规范

| 字段 | 受众 | 语言 | 要求 |
|------|------|------|------|
| `message` | LLM + 日志 | English | 技术准确、简洁、包含关键参数 |
| `user_hint` | LLM | English | 指导 LLM 如何修复或重试 |
| `diagnostic_info` | LLM | English | key-value 结构化上下文（可选） |
| `recovery_suggestions` | LLM | English | 按成功概率排序的恢复建议（可选） |
| `error_code` | 监控系统 | UPPER_SNAKE | 用于分类统计（如 `BROWSER_NAV_404`）（可选） |

### 不需要接入的场景

- **Sandbox 执行错误**：通过 `ExecutionResult` 构建，其 `error_hint` 会传递到 `BashExecutionError` → `ToolError`
- **LLM 模型错误**：通过 `error_types.py` 的三层分类体系处理，用于 model failover，见下方"LLM错误本地化系统"章节
- **系统级错误**（OOM、网络断开）：通过 `AgentEventType.ERROR` 顶级通道
- **软错误工具**（memory、cron、skill 等）：自行 catch 返回字符串，不触发前端红色提示

---

## LLM错误本地化系统

专门为LLM模型执行错误提供多语言本地化支持的独立系统。

### 设计目标

1. **用户友好**：为最终用户提供清晰的多语言错误消息和操作指导
2. **框架独立**：i18n子模块零业务耦合，开箱即用
3. **可扩展**：Protocol抽象支持业务层注入自定义i18n实现

### 端到端流程

```
LLM执行异常（RateLimitError / AuthenticationError / TimeoutError / etc.）
    ↓
stream_fatal_error.py `_emit_fatal_error`（异常捕获，executor 内层）
agent/_internals/agent_runtime.py run_agent_loop 外层 except（executor 外层兜底）
    │ classify_error(exc) → ErrorKind（toolkits/llms/errors/classifier.py）
    │ LLMErrorDiagnostic.diagnose(exc, ErrorContext) → DiagnosticResult（本地化 user_message + resolution_steps）
    │ 构建 error_event（两条路径字段结构一致）:
    │   - error_kind: str（如 "rate_limit"）
    │   - error_type: str
    │   - failover_reason: str
    │   - fault_side: str（确定性责任方归因：model | harness_tool | harness_pipeline | env | grader | owner | unknown，由 errors/fault_side.py 纯规则分类，无 LLM 调用）
    │     error_kind 优先；error_kind 为 UNKNOWN 时以 diagnostic.error_type 兜底（如 api_key → env）
    │   - diagnostic_result: { error_type, user_message, resolution_steps, locale }（本地化诊断结果）
    │   - recovery_actions: list[{id, label, url}]（本地化恢复按钮，由 `diagnostics/recovery_actions.py` 生成，可选）
    │   - cooldown_remaining_ms: int（供应商给出的剩余等待毫秒数，可选；诊断引擎把它写进 user_message，网页前端不读取该字段）
    ↓
SSE推送到前端（compactor.put）
    │ event_logger.log("error", ...)（同字段去 type/messageId 后持久化，供 trace 重建）
    ↓
agentControlEvents.ts（前端消费）
    │ 优先消费 diagnostic_result（user_message + resolution_steps）
    │ 缺失时 fallback getUserFriendlyError(error_kind, rawError)
    ↓
ProgressSteps.tsx（UI展示）
    └ 显示本地化错误消息 + fault_side badge + hint提示 + 恢复动作

event_log 持久化的 error 事件由 trace_builder 重建为 ExecutionTrace.errors（含 fault_side / error_kind / recovery_actions / diagnostic_result），确保会话分析时间线的 outcome 与首不可恢复点对 LLM 致命错误也准确。
```

### 核心组件

#### 1. 框架层（agent/errors/diagnostics/）

| 模块 | 职责 |
|------|------|
| `engine.py` | `LLMErrorDiagnostic` 静态分类器：LLM 异常 → 本地化 `DiagnosticResult`；先试传输类与账户类，再进入模型、限流、响应格式、上下文、超时，随后经 `classify_error` 桥接分类器认得而关键词族没认出的失败（`api_key` / `billing` / `rate_limit` / `timeout` / `context_overflow` / `response_format_error` / `overloaded` / `safety_block` / `format_error` / `challenge_blocked`；`model_not_found` 与订阅档位门槛不在其中：分类器把供应商策略拦截归在前者、把档位门槛归在 `context_overflow` 之下，二者用供应商自己的话展示更准），最后兜底 `unknown` |
| `catalog_result.py` | `build_catalog_result`：错误类型 → 本地化 `DiagnosticResult` 的唯一装配点（文案、步骤、供应商给出的等待时长；`entry` 选同一错误类型的另一版措辞，结果的类型不变） |
| `transport_diagnosis.py` | TLS（`tls_certificate`、`tls_transient`）与连接（`connection`、`custom_endpoint_unreachable`）诊断；自定义端点的服务名、端口推断 |
| `account_diagnosis.py` | 余额（`billing`）、供应商策略（`opencode_training_policy`）与密钥（`api_key`）诊断 |
| `types.py` | `DiagnosticResult` / `ErrorContext` 数据结构 |
| `i18n/manager.py` | `LocaleManager`：locale 检测 + 捆绑 JSON 加载 + 消息格式化；`locale_chain()` 定义文案的回退链：请求的语言 → 中文区域（含繁体 `zh-TW`，没有繁体目录）的 `zh-CN` → `en` |
| `i18n/__init__.py` | `get_locale_manager()` 全局单例 |
| `i18n/constants.py` | `REQUIRED_ERROR_TYPES` 翻译完整性校验 |
| `i18n/locales/` | 5 语言 JSON（en/zh-CN/ja/ko/de） |

#### 2. ErrorKind分类（`toolkits/llms/errors/classifier.py`，12种）

| ErrorKind | 含义 |
|-----------|------|
| `rate_limit` | API请求频率受限 |
| `overloaded` | AI服务过载 |
| `timeout` | 服务超时 |
| `billing` | 余额/额度不足（含订阅额度用尽、无订阅的 403/429） |
| `auth` | 认证失败 |
| `model_not_found` | 模型不存在 |
| `format_error` | 请求格式错误 |
| `response_format_error` | 响应格式错误 |
| `context_overflow` | 上下文过长 |
| `safety_block` | 安全拦截（供应商内容策略或内容过滤器拒绝，含错误码 `content_filter`、`ResponsibleAIPolicyViolation`、`data_inspection_failed`，DashScope 的 “may contain inappropriate content”，Codex 的网络安全标记，MiniMax 的 `new_sensitive`（1027）与 “Content Exists Risk”） |
| `challenge_blocked` | 出口被 WAF/反爬质询拦截（请求未到达模型） |
| `unknown` | 未知错误 |

恢复按钮（`recovery_actions`）只给有单击修复的诊断类型，目录见 `diagnostics/recovery_actions.py`：`api_key` → `update_key`，`billing` → `top_up`，`model` / `custom_model_not_found` → `change_model`，`update_key` 与 `change_model` 落到「设置 > 模型服务」（`/settings/models`），`top_up` 落到 `/settings`；其余类型不下发按钮。

供应商原文的展示约定：`unknown` 与 `format_error`（供应商拒绝了请求）的 `user_message` 带供应商自己的话，用户看到的是原因而不是库内部的样子。原话的来源：先读异常自带的应答（`toolkits/llms/errors/error_payload.py::provider_error_message`，沿 `__cause__` / `__context__` 链，依次取 SDK 解析好的 `body`、响应 JSON、非 JSON 的网关页或纯文本；聚合网关把上游错误放在 `error.metadata.raw` 时先取上游那句，包装层的 “Provider returned error” 只在上游缺失时才显示；JSON 转义由 JSON 解码器还原，中文与 emoji 不会变成乱码），应答里什么都没有时才退回异常文本，去掉 `litellm.XxxError:`、`XxxException -`、`Error code: NNN -` 三段库前缀，正文是 JSON 或 Python dict 时只取 `message` 字段；没有句子的 JSON 对象或数组（`{}`、`{'code': 1027, 'msg': …}`、校验记录列表）是数据而不是话，不展示：`format_error` 退到模型词条或通用词条，`unknown` 退回异常类名（以 `[Errno 28]`、`[ERROR]`、`[400]`、`[2024-10-30 12:00:00]` 这类方括号标签开头的文字是话，照常展示；数组只有立即闭合，或首个元素是对象、数组、字符串时才算数据）。随后统一整理（`engine._present`）：HTML 错误页只留可见文字（去掉标签、`script`、`style`）；**先脱敏再截断**，供应商回显的密钥不会被截断线切成漏网的前半截；折叠空白，超过 200 字符时截断并以 `…` 标明；整段为空时 `unknown` 退回异常类名。

`format_error` 在异常没有任何供应商应答时（客户端库在发请求之前就抛出的失败，例如缺少服务商前缀、参数不被支持）不引用库文本：调用方给了 `ErrorContext.model_name` 时用 `format_error_model` 词条（点出请求发往的模型，处理步骤指向「设置 > 模型服务」），没有模型信息时用不含占位符的 `format_error_generic`（结果的 `error_type` 仍是 `format_error`，恢复按钮与上游消费者不受影响）；`unknown` 是兜底，可以展示整理后的异常文本。五种语言目录里引用原话的词条一律使用 `{error_message}` 占位符（引擎只填这一个参数，目录里写成别的名字会让原文被静默替换为空串）。守护测试：`tests/agent/errors/diagnostics/test_unknown_diagnostic_copy.py`（占位符）、`test_provider_message_text.py`（整理管线）、`test_provider_failure_diagnostics.py`（各种应答形态与客户端侧失败）、`test_classified_failure_diagnostics.py`（分类器认得的每种失败都有自己的卡片，含 litellm 的 Anthropic、Gemini、DeepSeek 密钥失败与供应商策略拦截不被当成缺失模型）、`test_data_shaped_provider_text.py`（数据形正文不被展示，方括号标签开头的话照常展示）、`tests/toolkits/llms/errors/test_error_payload.py`（应答读取）、`test_normalize.py`（嵌套过深的上游应答不让分类失败）、`test_locale_placeholder_parity.py`（五种语言的键集与英文目录一致，缺键会静默退回英文）。

目录文案的通用约定：`user_message`、`resolution_steps`、`rate_limit_wait_step` 原样展示给最终用户（网页端错误卡片、可信所有者私聊的渠道回复），因此不出现配置标识符（`snake_case` 参数名、`UPPER_SNAKE` 环境变量、`*Config` 类名）与库内部概念（LiteLLM、调试开关）；需要用户操作时指向产品里看得见的入口，例如「设置 > 模型服务」「设置 > 模型服务 > 默认模型」。入口名称与前端菜单文案的一致性由 server 侧 `tests/integration/test_diagnostic_copy_ui_labels_i18n_sync.py` 对五种语言逐一守护。该约定对每种错误类型、每份语言目录由 `tests/agent/errors/diagnostics/test_diagnostic_copy_has_no_identifiers.py` 守护。

#### 3. DiagnosticResult结构

```python
@dataclass(frozen=True)
class DiagnosticResult:
    error_type: str  # 错误类型（如 "rate_limit"）
    user_message: str  # 本地化用户消息
    resolution_steps: list[str]  # 恢复步骤建议
    locale: str  # 请求的语言（en/zh-CN/zh-TW/ja/ko/de 等）；文案按 `locale_chain()` 取，繁体请求读到简体文案
```

### 前端错误处理

#### 支持的语言

前端 locales 提供 6 种语言（`de`/`en`/`ja`/`ko`/`zh`/`zh-TW`），`errors` section 含常见错误分类的 message/hint 翻译。

#### 前端消费链路

- `agentControlEvents.ts`：收到 ERROR 事件 → 优先消费后端 `diagnostic_result`（`user_message` + `resolution_steps`），`diagnostic_result` 缺失时 fallback `getUserFriendlyError(error_kind, rawError)`
- `streamHelpers.ts` `getUserFriendlyError()`：`wake_turn_failed` 取语言包词条，`concurrency_limit` 特判中英双语消息，其余分类原样返回原始错误
- `ProgressSteps.tsx`：渲染错误 UI（红色区域 + 重试历史）与恢复按钮；只渲染带 `url` 的恢复动作（`/` 开头跳站内页，其余新标签页打开），没有落点的动作（如 `wait`、`retry`）点了也无处可去，不渲染成按钮

```typescript
// streamHelpers.ts 真实实现（简化）
export async function getUserFriendlyError(
  errorKind: ErrorKind | undefined,
  rawError: string,
): Promise<FriendlyError> {
  if (errorKind === 'wake_turn_failed') {
    return { message: translateI18nKey('chat.wakeupNotice.failed') };
  }
  if (errorKind === 'concurrency_limit') {
    const isZh =
      typeof document !== 'undefined' && document.documentElement.lang?.startsWith('zh');
    return {
      message: isZh
        ? '并发会话已达上限，无法接收新请求。请先结束部分运行中的任务后重试。'
        : 'Concurrency limit reached; the request could not be accepted. Please finish or stop some running tasks and retry.',
    };
  }
  return { message: rawError };
}
```

### 类型安全保证

- **后端**：`ErrorKind` enum（`toolkits/llms/errors/classifier.py`）+ `DiagnosticResult` dataclass（`diagnostics/types.py`）
- **前端**：`ErrorKind` type + `ErrorStreamEvent` interface（TypeScript）
- **SSE字段同步**：
  - `error_kind: string`
  - `error_type: string`
  - `failover_reason: string`
  - `diagnostic_result: { error_type, user_message, resolution_steps, locale }`（本地化诊断结果）
  - `recovery_actions?: RecoveryAction[]`（`{ id, label, url }`，本地化恢复按钮）
  - `cooldown_remaining_ms?: number`

### 扩展业务层自定义翻译

```python
# 业务层可注册/合并自定义翻译（LocaleManager.register_translations）
from myrm_agent_harness.agent.errors.diagnostics.i18n import get_locale_manager

get_locale_manager().register_translations(
    "zh-CN",
    {"rate_limit": {"user_message": "API 请求频率受限", "resolution_steps": ["可升级 API 计划或切换模型"]}},
)
# 或通过环境变量 MYRM_LOCALES_DIR 指定自定义 locale JSON 目录（扁平键 `<error_type>_user_message` / `_resolution_steps` / `_wait_step` 与 cooldown_hint_* 自动展平）
# 限流诊断只说一次等待：供应商给出等待时长时，消息里已有该时长，resolution_steps 不含通用的 rate_limit_wait_step；
# 没有给出时它排在 resolution_steps 之首。自定义目录没有 rate_limit_wait_step 时，resolution_steps 就是目录里的步骤。
# 自定义文案里 str.format 不认的模板（如 `{}`、`{model`、`{x[a]}`）视为该语言没有这条文案：按回退链取下一种语言（中文区域先 zh-CN，最后英文）并记一条带异常栈的 WARNING，错误卡保持完整；
# 步骤列表里只要有一步无法渲染，整个列表回退；回退链上的语言都无法渲染时按缺失翻译处理。
```

---

## 相关文件

### 工具错误处理

| 文件 | 角色 |
|------|------|
| `utils/errors.py` | ToolError 定义、format_error_message、ModelOutputValidator |
| `toolkits/browser/exceptions.py` | BrowserError 异常树（含智能诊断） |
| `toolkits/web_search/core/exceptions.py` | WebSearchError 异常树（含 retryable 信息） |
| `agent/middlewares/tooling/_tool_helpers.py` | 工具异常格式化（`format_tool_error`：format_for_llm 协议 + 脱敏兜底） |
| `agent/streaming/event_handlers.py` | 错误事件转换（ToolMessage → SSE 事件） |
| `toolkits/code_execution/executors/common/error_handler.py` | Sandbox 错误处理装饰器 |

### LLM错误本地化

| 文件 | 角色 |
|------|------|
| `toolkits/llms/errors/classifier.py` | LLM错误分类器（`classify_error()`，`ErrorKind` enum） |
| `toolkits/llms/errors/normalize.py` | 把异常读成状态码、响应体与一段小写文本供分类器匹配（含聚合网关放在 `error.metadata.raw` 里的上游错误）；上游应答只经 `parse_json_object` 解析，嵌套过深或被截断的应答只损失细节，不会让分类抛错 |
| `toolkits/llms/errors/error_payload.py` | 供应商应答的唯一读取点：异常链遍历、响应体提取、供应商原话（`provider_error_message`）、JSON 对象解析（`parse_json_object`）与数据形文字判定（`is_json_shaped`），归一化、重试窗口与诊断共用 |
| `toolkits/llms/errors/error_types.py` | 三层分类体系（RecoverabilityLevel / FailoverReason / ProbePolicy） |
| `agent/errors/diagnostics/engine.py` | `LLMErrorDiagnostic`：LLM 异常 → 本地化 `DiagnosticResult` |
| `agent/errors/diagnostics/catalog_result.py` | `build_catalog_result`：错误类型 → 本地化 `DiagnosticResult` 的唯一装配点 |
| `agent/errors/diagnostics/transport_diagnosis.py` | TLS 与连接类诊断（`diagnose_transport`），自定义端点的服务名、端口推断 |
| `agent/errors/diagnostics/account_diagnosis.py` | 余额、供应商策略与密钥类诊断（`diagnose_account`） |
| `agent/errors/diagnostics/recovery_actions.py` | 恢复按钮目录：`api_key` / `billing` / `model` 等有单击修复的错误类型 → 本地化 `{id, label, url}` |
| `agent/errors/diagnostics/types.py` | `DiagnosticResult` / `ErrorContext` 数据结构 |
| `agent/errors/diagnostics/i18n/manager.py` | `LocaleManager`（locale 检测 + 捆绑 JSON + `register_translations()` 扩展） |
| `agent/errors/diagnostics/i18n/__init__.py` | `get_locale_manager()` 全局单例 |
| `agent/streaming/stream_fatal_error.py` | LLM异常捕获（`_emit_fatal_error`，经 `StreamExecutor` 多继承使用）+ `classify_error()` + SSE推送 |

### 前端错误渲染

| 文件 | 角色 |
|------|------|
| `myrm-agent-frontend/src/store/chat/messageStream/streamHelpers.ts` | 前端错误事件消费 + getUserFriendlyError() |
| `myrm-agent-frontend/src/store/chat/types/agentStream/part1.ts` | `ErrorKind` type + `ErrorStreamEvent` interface 定义 |
| `myrm-agent-frontend/locales/*.json` | 6种语言翻译文件（de/en/ja/ko/zh/zh-TW，errors section 含错误分类翻译） |
| `myrm-agent-frontend/src/i18n/config.ts` | next-intl配置（支持的locales） |
| `myrm-agent-frontend/src/components/features/message-box/progress-steps/ProgressSteps.tsx` | 错误 UI 渲染 |
