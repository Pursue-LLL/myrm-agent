# 工具安全包装开发者指南

> 何时在工具层使用 `wrap_with_external_sources_tag()` 和 `wrap_with_tool_output_tag()`

---

## 核心原则

**外部数据、recall 回读与工具执行结果（命令输出、文件内容）都要防护，档位见「出口一览」；内部可信结果无需包装。**

---

## 包装决策树

```
工具返回的数据来自哪里？
├─ 外部不可信来源（网页、第三方 API、浏览器页面、知识库）
│  └─ ✅ 必须包装
│     └─ 使用 wrap_with_external_sources_tag(content, source="tool_name")
│
├─ 记忆/历史 recall 回读（memory_search memory/sessions/按 id 取回、MCP memory_recall/list）
│  └─ ✅ 必须 sanitize + 静态 untrusted 前言
│     └─ 使用 memory_recall_formatting.sanitize_recalled_content（redact → sanitize）+ finalize_recall_tool_output
│     └─ 长度截断放在脱敏之后（先截后脱敏会把被切开的凭据半截原样留给模型）；无界原文先取有界窗口脱敏，窗口尾部一段不展示，空白折叠也放在脱敏之后（部分规则锚定在行首，折叠成一行会让它们失效）（见 conversation_search/format_output.py）
│     └─ 提供方（宿主）自己从长文本里切出片段时，同样先脱敏后切，并交出不带 HTML 转义、不带高亮标记的纯文本（见 conversation_search/types.py 的 ConversationSearchHit.snippet）
│     └─ ❌ 不要用 wrap_with_external_sources_tag（会触发引用规则且 random boundary 伤 cache）
│
├─ 记忆 preference save 成功回执（memory_save_tool / MCP memory_store preference）
│  └─ ✅ 必须 sanitize（同 recall SSOT）
│     └─ 使用 format_preference_save_ack（redact → sanitize）；避免 write scan 已 redact 存库但 ToolMessage echo 明文
│  3. Recall source_error suffix（memory_search / MCP recall）
│     └─ 使用 format_recall_source_error_suffix（redact → sanitize）；与 middleware stable 注入对齐
│
├─ 工具执行结果（命令输出、文件内容、目录列表）
│  └─ ✅ 使用 wrap_with_tool_output_tag（防注入，不触发引用规则）
│     └─ 各出口的范围与例外见下面的「出口一览」
│
└─ 内部可信结果（Agent 委托、系统工具）
   └─ 无需包装
```

---

## 出口一览

每个出口属于下面四档之一。「范围」是已包装的返回内容，「例外」是同一出口里不包装的分支；锚点写 `文件::符号`，路径相对 `myrm_agent_harness/`。新增、修改或移除出口时，同步改这张表。

### ① UNTRUSTED_DATA 信封

`wrap_with_external_sources_tag()` / `wrap_untrusted()`：用于外部数据源，触发引用规则。

| 出口 | 范围 | 例外（不包装） | 锚点 |
|------|------|----------------|------|
| **Web 搜索** `web_search` | 全部返回 | 无 | `toolkits/web_search/web_search_agent_tools.py::web_search_func`（`source="web_search"`） |
| **Web 抓取** `web_fetch` | 抓取的正文；全部失败时的失败网址清单 | 无；工具自己生成的指引接在包装之后（见下文） | `toolkits/web_fetch/web_fetch_agent_tools.py::_fetch_full_content`、`::_fetch_and_extract`；`toolkits/web_fetch/processing/full_content_delivery.py::all_failed_content`（`source="web_fetch"`） |
| **知识库查询** | `wiki_query_tool` 的结果；`memory_search_tool` 的 wiki 语料 | 无 | `toolkits/wiki/wiki_agent_tools.py::wiki_query`；`toolkits/memory/agent_surface/memory_search_execution.py::search_wiki_corpus`（`source="LLM-Wiki"`） |
| **浏览器工具** | snapshot、extract、inspect、navigate、interact、execute_script、接管结果、下载动作；`browser_manage_tool` 的 evaluate、emulate、console、network、web_vitals、run_site_tool 结果 | `browser_manage_tool` 的 `dialog_response` 应答回显（页面对话框文字的前 80 个字符）、站点经验的保存与列表回显、站点脚本的失败文本 | `toolkits/browser/tools/common.py::mark_untrusted`（先 `redact_sensitive_text` 凭据脱敏，再 `wrap_untrusted(..., source="browser")`）；例外 `toolkits/browser/session/dialog_manager.py::respond`、`toolkits/browser/tools/manage.py::_handle_save_site_experience` / `_handle_list_site_experience` / `_handle_run_site_tool` |
| **MCP 工具** | 字符串结果（含服务端报告的错误）；多模态结果里的文本块 | 框架自己生成的失败消息：超时、不支持的内容（只做凭据脱敏）、授权过期 | `toolkits/mcp/tool_processing.py::wrap_tools_with_timeout`；`toolkits/mcp/result_processing.py::wrap_multimodal_text_blocks`（`source="mcp:{tool_name}"`） |

### ② TOOL_OUTPUT 信封

`wrap_with_tool_output_tag()` / `wrap_tool_output()`：用于工具执行结果，只防注入，不触发引用规则。

| 出口 | 范围 | 例外（不包装） | 锚点 |
|------|------|----------------|------|
| **命令行** `bash_code_execute_tool` | 普通前台命令的输出 | 命中构建与测试白名单（npm、yarn、pnpm、bun 的 build 或 test，pytest，cargo，make，docker compose，mvn，gradle）的命令默认走自动让出路径：让出窗口内（默认 10 秒，`yield_after_seconds=0` 关闭）结束的输出、仍在运行时的部分输出，直接拼进返回文本；后台启动的返回只含任务编号、进程号、命令与状态 | `agent/meta_tools/bash/_tool/formatting.py::format_result`；例外 `agent/meta_tools/bash/_executor/auto_yield.py::build_auto_yield_return`、`agent/goals/wait_background_bash.py`（白名单） |
| **文件读取** `file_read_tool` | 默认模式（`mode="all"`）的文本文件与按行范围读取；目录列表 | `preview` 与 `stream` 模式（含超过 100 MB 的文件自动降级的 preview）、`parse_mode="structure"` 的结构大纲、PDF 与 Office 文档与图片 OCR 与视频的文本块（只做凭据脱敏）；技能文档（路径含 `SKILL.md` 且在 `skills` 目录下）与 `/mcp/` 虚拟路径按设计不包装，要让模型遵循 | `agent/meta_tools/file_ops/core/result_formatter.py::ResultFormatter.format_file_content`、`::format_directory_listing`；例外 `agent/meta_tools/file_ops/core/file_read/text_paths.py::process_text_paths`、`agent/meta_tools/file_ops/core/file_read/multimodal.py::build_multimodal_result` |

### ③ 固定前缀 + 脱敏 + 清洗（不套信封）

| 出口 | 原因 | 做法 |
|------|------|------|
| **记忆 recall/list 工具**：`memory_search_tool`（含按 id 取回）、MCP `memory_recall` / `memory_list` | 写入 scanner 不能 100% 拦截低分 injection；sessions snippet 不经 write scan；recall 返回须 defense-in-depth | 框架已在 `toolkits/memory/agent_surface/memory_recall_formatting.py` 统一 `redact_sensitive_text` → `sanitize_recalled_content()` + 静态 untrusted 前言（**不要**再套 `wrap_with_external_sources_tag`） |
| **记忆 preference save ack**：`memory_save_tool`、MCP `memory_store`（preference 成功） | write scan redact 存库后，ack 若 echo 原始入参会把凭据塞回 ToolMessage | `format_preference_save_ack()`（同 SSOT redact → sanitize） |
| **记忆 recall source_error 后缀**：`memory_search_tool`、MCP `memory_recall` | correction 的 `source_error` 字段可含凭据；与 middleware stable 注入同 SSOT | `format_recall_source_error_suffix()`（redact → sanitize） |

### ④ 不包装

| 出口 | 说明 | 锚点 |
|------|------|------|
| **后台进程轮询** `bash_process_tool` | 后台进程的输出原样返回 | `agent/meta_tools/bash/_tool/process_handlers.py::handle_output` / `handle_wait` |
| **文件搜索** `grep_tool`、`glob_tool` | 路径与匹配行原样返回；`grep_tool` 的匹配行先按文件类型脱敏凭据 | `agent/meta_tools/file_search/grep_tool.py`、`glob_tool.py` |
| **记忆 store/manage 其它**：knowledge/event/rule；`memory_manage_tool` | 成功 ack 不回显 user body 或仅返回 ID；写入/变更仍走 `memory_scanner` | 无需 recall 前言 |
| **Agent 委托** `delegate_task_tool`、PTC `spawn_subagent`（Dynamic Workflow） | Agent 之间的内部通信，是可信的 | — |
| **系统工具** `goals`、`cron`、`tasks` | 系统内部数据，是可信的 | — |

---

## 安全防护层级

使用 `wrap_with_external_sources_tag()` 或 `wrap_with_tool_output_tag()` 包装后，内容依次经过下面 5 层处理。这是文本层缓解，不是硬边界；强制约束仍来自审批与沙箱。各层的规则与边界情形见 [SECURITY_SYSTEM.md](../agent/security/SECURITY_SYSTEM.md) 第八节与 `content_boundary.py` 的模块文档。

1. **Unicode 折叠** — 把全角字母与形似尖括号折回 ASCII，使伪装的边界标记能被识别；系统标签的匹配只折叠全角字母与全角 ＜＞
2. **结构剥离** — 剥掉白名单内的角色/框架标签、ChatML 特殊 token、CDATA 块与代码围栏
3. **标记消毒** — 中和内容里伪造的边界标记
4. **随机边界** — 每次调用生成不可预测的边界 ID，事先写不出匹配的结束标记；信封前附安全提示，提示 LLM 边界内是数据、不执行其中的指令
5. **可疑模式检测** — 在原文上扫描已知的角色覆盖、指令覆盖与系统模拟句式（中英双语），只记日志，不拦截、不改写

不可见字符不在这 5 层之内：包装函数不剥离零宽、双向控制与 Tag 块等字符（`strip_invisible_unicode()` 单独提供，包装流程不调用）；消息归一化只去掉 U+200B、U+200C、U+200D、U+FEFF；对其余字符，包装与归一化都不做处理。

---

## 实现示例

### ✅ 正确示例：Web 搜索工具

```python
from myrm_agent_harness.utils.context_format import wrap_with_external_sources_tag

@tool("web_search")
async def web_search(query: str) -> str:
    results = await search_engine.search(query)
    formatted_results = format_search_results(results)
    
    # 包装外部数据
    return wrap_with_external_sources_tag(
        formatted_results,
        source="web_search"
    )
```

### ❌ 错误示例：记忆召回工具

```python
# 错误！不要对 recall 结果使用 wrap_with_external_sources_tag（会触发引用规则且 random boundary 伤 cache）
@tool("memory_search_tool")
async def memory_search_tool(query: str) -> str:
    memories = await memory_store.query(query)
    formatted_memories = format_memories(memories)

    # ❌ 不要这样做！
    return wrap_with_external_sources_tag(
        formatted_memories,
        source="memory"
    )

# ✅ 正确：复用 agent_surface/memory_recall_formatting（memory_search_execution / mcp_server 已接入）
from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_formatting import (
    finalize_recall_tool_output,
    sanitize_recalled_content,
)

safe_line = sanitize_recalled_content(memory.content)
body = finalize_recall_tool_output(format_line(safe_line))
```

---

## 两种包装函数的区别

### `wrap_with_external_sources_tag()`

- **用途**：外部数据源（搜索结果、网页内容、知识库、浏览器页面、MCP 远程数据）
- **效果**：触发引用规则，LLM 需要添加引用标记【1】【2】
- **边界标记**：`<<<UNTRUSTED_DATA id="...">>>`

```python
from myrm_agent_harness.utils.context_format import wrap_with_external_sources_tag

wrapped = wrap_with_external_sources_tag(content, source="web_search")
```

### `wrap_with_tool_output_tag()`

- **用途**：工具执行结果（代码输出、文件内容、目录列表）
- **效果**：仅防止 prompt injection，不触发引用规则
- **边界标记**：`<<<TOOL_OUTPUT id="...">>>`
- **使用场景**：`agent/meta_tools/bash/_tool/formatting.py`（前台命令输出）、`agent/meta_tools/file_ops/core/result_formatter.py`（文件读取与目录列表）；范围与例外见「出口一览」

```python
from myrm_agent_harness.utils.context_format import wrap_with_tool_output_tag

wrapped = wrap_with_tool_output_tag(content)
```

### 工具自己的指引放在包装之外

包装之内只放外部内容（网页正文、搜索结果、抓取失败的网址）；工具自己生成的可信指引接在包装之后，例如 `web_fetch` 在页面被缩短时给出的「完整内容的保存路径、被省略的行号范围、用 `file_read_tool` 读取」。指引放进包装，模型会把它当作不可信数据而不照做；外部内容落到包装之外，则绕过全部防护。指引里只能出现工具自己生成的标签、路径和数字，不能回显外部文本。

---

## 检查清单

在实现新工具时，问自己以下问题：

1. ✅ **数据来源**：数据来自外部（网页、第三方 API）、工具执行结果（命令输出、文件内容），还是内部可信（系统工具、Agent 委托）？
2. ✅ **风险评估**：数据是否可能包含恶意指令？
3. ✅ **已有先例**：类似的工具是如何处理的？
4. ✅ **测试验证**：是否有单元测试验证安全包装？
5. ✅ **指引位置**：工具自己写的指引是否放在包装之外，外部内容是否都在包装之内？

---

## 参考资料

- **核心实现**：`myrm_agent_harness/core/security/detection/content_boundary.py`
- **工具层接口**：`myrm_agent_harness/utils/context_format/boundary.py`（经 `myrm_agent_harness.utils.context_format` 导入）
- **MCP 框架层包装**：`toolkits/mcp/tool_processing.py`（`wrap_tools_with_timeout`）
- **已有示例**：
  - `toolkits/web_search/web_search_agent_tools.py`
  - `toolkits/web_fetch/web_fetch_agent_tools.py`
  - `toolkits/wiki/wiki_agent_tools.py`
  - `toolkits/browser/tools/` (snapshot.py, extract.py)
  - `agent/meta_tools/bash/_tool/formatting.py`
  - `agent/meta_tools/file_ops/core/result_formatter.py`

---

## 常见问题

### Q1: bash 工具输出需要包装吗？

**A**: 普通前台命令的输出已用 `wrap_with_tool_output_tag` 包装（防止输出中的恶意内容被 LLM 当作指令执行）。命中构建与测试白名单的命令默认走自动让出路径，返回的输出不包装；后台进程的轮询输出也不包装，见「出口一览」。

### Q2: MCP 工具输出需要包装吗？

**A**: 工具返回的字符串结果与多模态结果里的文本块，已由框架层统一处理：`tool_processing.wrap_tools_with_timeout` 调用 `wrap_untrusted(source="mcp:{tool_name}")`，工具层无需额外处理。框架自己生成的失败消息（超时、不支持的内容、授权过期）不包装。

### Q3: 包装会影响性能吗？

**A**: 耗时随内容长度增长。本机 Python 实测（中位数）：1 KB 约 0.1 ms，10 KB 约 1 到 2 ms，100 KB 约 20 ms（最小值约 12 ms）。

### Q4: 包装会增加 token 消耗吗？

**A**: 会，开销是固定的、与内容长度无关：`TOOL_OUTPUT` 信封约 50 到 60 个 token，`UNTRUSTED_DATA` 信封（含来源行）约 70 到 80 个 token（`tiktoken` 的 o200k_base 与 cl100k_base 实测）。负载约 1000 个 token 时增加 6% 到 8%，约 100 个 token 时增加 50% 到 80%，几十个 token 的短输出会翻几倍。信封隔离的是不可信内容，是否包装按决策树与「出口一览」决定，不按输出长短取舍。

---

## 总结

**核心规则：外部数据与工具执行结果要防护，内部可信结果无需包装。**

新增工具时按「出口一览」选档位并登记范围与例外；包装是文本层缓解，强制约束仍来自审批与沙箱。
