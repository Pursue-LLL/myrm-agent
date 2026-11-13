# utils/

## Overview
Utility library exports. Public interface for the utils module providing commonly used helper functions.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `shell_quote.py` | Core | Universal cross-platform shell argument quoting (POSIX, Windows cmd.exe CommandLineToArgvW, PowerShell). | ✅ |
| __init__.py | Package | Utility library exports. Public interface for the utils module providing commonly used helper functi | ✅ |
| chat_utils.py | Core | Chat utility functions. Provides business-config-independent chat history conversion and content text extraction: `extract_text_content` (str / block-list / JSON; a list without text blocks yields `""`, never its repr), `extract_answer_text` (LLM 响应答案提取，先剥离内联 think 标签块，再兼容 reasoning 模型 content 空时回退 `reasoning_content`) and `extract_completion_text` (LLM 传输层 OpenAI 形态补全响应 dict 的文本提取，兼容 `choices[0].message.content` / Anthropic 块列表 / `reasoning_content` 回退). | ✅ |
| json_parsing.py | Core | Robust LLM reply JSON extraction. `parse_llm_json_object` / `parse_llm_json_list` 容错提取 JSON 对象/数组：兼容 markdown fence、prose 包裹、字符串内裸控制字符、尾逗号、多候选时取最后可解析容器；结构解析失败时用 `json_repair` 兜底容错单引号字符串、无引号 key 与内联注释——兜底仅作用于结构有界候选并带嵌套深度预算，深度超限/`RecursionError` 输入优雅降级为 `None` 而非崩溃，且以 `skip_json_loads=True` 跳过必然失败的内置预验证（结构层已先行验证过）；平衡扫描器单引号感知：容器内单引号字符串中的 `}`/`]` 不会截断候选块、结构外撇号视为 prose 不吞对象，保证单引号 JSON 不静默丢数据；`parse_llm_json_object` 支持 `require_key` 过滤——仅取含指定键的对象，供 verifier/语义判定等"必须含某字段"契约复用. | ✅ |
| json_args_repair.py | Core | Tool-call args 修复与出站隔离（replay-poisoning 防御）。`repair_json_args` 对单条畸形 args 做确定性转义级修复（严格解析→控制字符转义→尾逗号剥离→截断闭合，复用 json_parsing 底层原语；结果必须解析为 JSON object），不猜测内容；`quarantine_invalid_tool_calls` 将 AIMessage.invalid_tool_calls 升级为合法 tool_call 声明（可修复→修复后 args；不可修复→空 args + 字段路径式结构诊断），进入即无条件清空 invalid 桶（重复 id/不可升级条目直接丢弃，valid 声明优先），返回 `(errors, changed)`，同步 additional_kwargs raw payload——畸形原文不再随 langchain 序列化回喂 provider（`_convert_message_to_dict` 实证会原样回传 invalid_tool_calls）。幂等确定性，供 dangling 修复管线与 ToolNode args guard 共用. | ✅ |
| coercion.py | Core | Defensive numeric coercion utilities. Provides parse_float, parse_int, parse_timeout handling inf/nan/negative/non-numeric inputs. | ✅ |
| context_format/ | Core | Context formatting subpackage (collection, token budget, assembly, safety boundary; `__init__.py` is the facade). `format_documents_with_metadata` labels each source with the number its `index_for` returns — inside a run that is `SourceTracker.index_for`, so the number the model reads is the index of the source card; without one it counts from 1. `wrap_with_external_sources_tag` adds UNTRUSTED boundary + dual-format citation reminder (e.g. [1] or 【1】) for web/wiki/fetch tool outputs. | ✅ |
| device_fingerprint.py | Legacy | Pure utility for device identification. Retained for migration only; superseded by encryption_key.py | ✅ |
| encryption_key.py | Core | Local-mode encryption key resolution: env var → file → auto-generate. Portable, no hardware binding | ✅ |
| document_utils.py | Core | Document object utilities. Provides LangChain Document front matter parsing, clean content extractio | ✅ |
| errors.py | Core | Framework-level error handling. ToolError exposes ``error_category`` from ``diagnostic_info`` for SSE/metrics; ``format_for_llm`` protocol; message + diagnostics redacted (credentials masked) at construction and in format_for_llm output. | ✅ |
| event_utils.py | Core | Provides dispatch_custom_event. | ✅ |
| files.py | Core | Pure file URL parsing utilities. No business logic dependencies. | ✅ |
| fuzzy_match.py | Core | Generic fuzzy matching module: the public API (`fuzzy_find`, `fuzzy_replace`) of the 8-strategy progressive chain (+Unicode preprocessing + escape-drift detection) for LLM-generated code variations; `min_confidence` skips the weaker strategies, and `CONTENT_PRESERVING_MIN_CONFIDENCE` keeps only the six that match the fragment's own text (the file edit tool passes it; `block_anchored` and `context_aware` let the lines between the anchors differ). `fuzzy_replace` reports a match whose text the content does not hold verbatim as a failure, never as an unchanged "success". | ✅ |
| _fuzzy_strategies.py | Core | The strategy chain behind `fuzzy_match`: Unicode normalization and the eight finders (`STRATEGIES`: name, finder, confidence, in the order they are tried). | ✅ |
| closest_lines.py | Core | Failure hint of the text-replacement tools: `find_closest_lines` lists the lines of a file nearest to the text that was not found, with line numbers, so the model resends the text exactly. | ✅ |
| hash_utils.py | Core | Unified hash utilities. High-performance document content hashing with multiple strategies (md5, sha | ✅ |
| image_utils.py | Core | Central media processing utilities (image/video/audio). Used by context_management, MediaFilterProcessor, and stream recovery to prevent overflow and multimodal rejection errors. | ✅ |
| log_rotation.py | Core | Agent utilities layer, used by audit logging and any growing log files. | ✅ |
| logger_utils.py | Core | Unified logging utilities. Provides consistent log format and convenience methods (step/success/erro | ✅ |
| locale.py | Core | BCP-47 locale normalization and Chinese-family detection (LocaleResolver SSOT): a Chinese tag resolves to `zh-TW` when its script subtag is Hant (without a script subtag: its region is TW, HK or MO) and to `zh-CN` otherwise; `is_chinese` is true for both | ✅ |
| response_locale.py | Core | Agent output locale/formality suffix from engine_params.response_locale_policy | ✅ |
| lru_cache.py | Core | LRU cache utility. OrderedDict-based LRU cache implementation with TTL support. | ✅ |
| markdown_frontmatter.py | Core | Markdown YAML frontmatter parse/preserve helpers shared by vault write guard, toolkits wiki, server wiki import and the server knowledge pack; `FRONTMATTER_BLOCK_RE` finds the block after an optional UTF-8 BOM, and the parsed body carries no BOM, so a page the system rewrites (repair, demote, approve) loses its BOM | ✅ |
| content_sniff.py | Core | Payload classification SSOT shared by the web_fetch tiers, the binary router, the file parsers' format sniffing and the Wiki source loader: `classify_payload(content_type, body)` decides `PayloadKind` WEB / TEXT / BINARY (a format signature beats any declared type; declared HTML and text types are trusted; anything else is sniffed the way browsers do), `magic_extension` names a format from its signature, `zip_file_extension` names the document a zip container holds. Reads only the first 1445 bytes for classification and at most 256 bytes of a zip's declared type; an unreadable archive is a plain `.zip`, never an error. | ✅ |
| mime_types.py | Core | Centralized image MIME type utilities: extension ↔ MIME mappings and magic-bytes detection (detect_image_mime, extension_for_mime) and `VISION_IMAGE_MIME_TYPES`, the four formats a vision model takes (BMP is detected but not among them). | ✅ |
| network.py | Core | Pure network utilities. Get local IP using UDP socket (no actual data sent). | ✅ |
| rwlock.py | Core | General-purpose read-write lock concurrency primitive for multi-reader single-writer scenarios. | ✅ |
| text_cleaner.py | Core | Text cleaning utilities. Removes noise and irrelevant information from content to improve quality. | ✅ |
| text_sanitizer.py | Core | LLM streaming output sanitizer. Four-layer filtering (reasoning blocks, orphan tags, tool-protocol tags, control characters) for model output via `sanitize_text`; `strip_control_chars` exposes the control-character layer alone for user-authored text, where tags are content. | ✅ |
| text_utils.py | Core | Text processing utilities: token counting, language detection, token-boundary truncation, `smart_truncate` (head+tail truncation whose cut `truncation_window` chooses), and output sanitization (ANSI, binary output, echoed boundary markers, Markdown fences). | ✅ |
| tiktoken_tables.py | Core | Bundled tiktoken vocabularies (`cl100k_base`, `o200k_base`, `p50k_base` in `_tiktoken_tables/`, stored under the file names tiktoken's cache expects): `get_encoding` / `encoding_for_model` point tiktoken's cache at them unless the host names its own cache (`TIKTOKEN_CACHE_DIR` / `DATA_GYM_CACHE_DIR`), so token counting needs no download, in a packaged desktop app or behind a firewall. The one place that reaches tiktoken. | ✅ |
| truncation_window.py | Core | Where head+tail truncation cuts. `truncation_window` returns the slices to keep within a character budget (cuts snap to line boundaries, the tail share grows when the end holds errors, JSON closures or summaries), `apply_truncation_window` joins them around a marker, `has_important_tail` flags a diagnostic tail. `smart_truncate` composes them; a caller that must point at the omitted lines uses the window directly so the cut and the pointer cannot disagree. | ✅ |
| tool_dynamic_hints.py | Core | LangChain tool `with_dynamic_hints` decorator — shared by agent and toolkits without cross-layer imports. | ✅ |
| token_estimation.py | Core | Message-level tokens (including the reasoning text of the signed `thinking_blocks` a message replays) + full tool-schema estimates for the context breakdown and compress preflight; description-only approximation for the Turn-1 inventory script | ✅ |
| tree_truncator.py | Core | Tree Truncator (Smart Budget-Aware Truncation). Truncates ARIA accessibility trees to a token budget by role weight, keeping every retained node structurally intact. | ✅ |
| os_compat.py | Core | Cross-platform process groups (`get_process_group_kwargs`, `kill_process_group`, `kill_spawned_group`, `terminate_process_graceful`; `kill_process_group` finds the group through the child's pid and so reaches nothing once the child has exited and been reaped while a descendant still runs, `kill_spawned_group` addresses the group a child was started in by that pid and still reaches it; use it for a child this code started with `get_process_group_kwargs()` and may have to stop after it exited, and `kill_process_group` for a live pid whose group this code did not create; the pid-reuse risk of `kill_spawned_group` is in its docstring), and `SIGKILL`: the force-kill signal that exists on Windows too (there `SIGTERM`, which `taskkill /F` makes a hard kill). Never name `signal.SIGKILL` outside `os.killpg`. | ✅ |
| process_start.py | Core | A process's start time that stays comparable across system clock adjustments (`start_stamp`): on Linux psutil derives start times from the wall clock, so the boot time is removed there; on macOS and Windows the start time is returned as it is. Compare two stamps with a tolerance, not for equality, and build the `psutil.Process` for every read (a process object keeps the start time it first reported, and `psutil.process_iter` objects are cached). Shared by the browser ownership stamp and the background job termination; psutil is imported when a stamp is read, so the module imports without it. | ✅ |
| url_syntax.py | Core | The one canonical spelling of an outbound URL and the syntax check behind it (`parse_outbound_url`, `parse_outbound_hostname`, `canonical_hostname`, `SSRF_ALLOWED_SCHEMES`): UTS 46 mapping with Punycode labels, legacy numeric IPv4 as dotted decimal, compressed IPv6 without brackets, one trailing dot dropped, ports as plain numbers. A URL with parser-confusing characters, a percent-encoded host, a malformed authority or an invalid host or port has no canonical form and is refused. Classifiers judge the canonical host and dial sites dial the canonical URL, so both name the host the client connects to. No hostname blocklist, so policies that admit private hosts share it with the cloud policy. | ✅ |
| url_utils/ | Core | URL 工具子包：parsing（规范化/类型判断）、blocking（SSRF 黑名单/动态主机）、security（scheme/主机校验、外泄检测、脱敏）；`__init__.py` 是唯一门面 | ✅ |

Workspace file enumeration lives in `toolkits/filesystem_suggest/indexer.py` (SSOT for `@` suggest and browse search).

| Submodule | Description |
|-----------|-------------|
| crypto/ | Config encryption utilities. |
| db/ | Database utilities for SQLite migration management. |
| media/ | Media utilities for image/video compression. |
| runtime/ | Agent run() lifecycle control parameters. All based on ContextVar for request-level isolation. |
| token_economics/ | LLM call full-chain economic metrics: token usage tracking (7 token types), cost calculation, and bu |

## Key Dependencies

- `langchain_core` — message types, document types, runnables (used by chat_utils, token_estimation, context_format, etc.)
- `json_repair` (json-repair) — LLM dirty JSON salvage tier for `utils/json_parsing.py` `parse_llm_json_object` / `parse_llm_json_list` (single quotes / unquoted keys / inline comments), with graceful degradation when absent
