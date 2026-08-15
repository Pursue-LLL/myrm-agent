# utils 模块架构


---

## 架构概述

业务特有工具函数模块，提供错误处理、响应格式化、文件操作、聊天格式转换、图片压缩等核心能力。是整个系统的通用工具层，被各模块广泛使用。专注通用性和可复用性。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|-----|------|------|-------|
| `errors.py` | 核心 | `MyrmError`、`StandardHTTPException`、`register_exception_handlers`、HTTP 异常快捷函数（validation/not_found/auth/permission/conflict/internal/service_unavailable/external）和 LLM/embedding 依赖错误分类。开发模式（DEBUG=true）下错误响应包含完整堆栈追踪。注：`ToolError` 由框架层提供（`myrm_agent_harness.utils.errors`） | — |
| `response_utils.py` | 核心 | `success_response`、`list_response`、`paginated_response` | — |
| `files_utils.py` | 核心 | `extract_file_id_from_url`、`read_image_as_base64`（通过 FilesService + StorageProvider 统一存储访问） | — |
| `media_file_reader.py` | 核心 | `read_uploaded_media_file_content`：为 harness `FileContentReader` 注入 `/api/media/files/{id}/content` 字节（VisionFallback + MediaResolver） | — |
| `chat_utils.py` | 核心 | `ChatHistoryReq`/`ChatHistory`、`convert_chat_history`（前端 → LangChain）、`preprocess_inbound_multimodal_query`（非 Web 渠道入站多模态 query 预处理，text-only 主模型时走 `_process_human_content`）、`_process_human_content`/`_process_image_item`（图像自适应降级路由 Vision Fallback，使用辅助 vision model 将图片转文本，并通过 SSE 发送 analyzing_image 状态事件；包含 Reactive Compress 逻辑，大图自动压缩后传输）；LLM 响应文本提取（`extract_answer_text`、`extract_litellm_answer_text` 直接复用框架层 SSOT）；`parse_judge_json`（业务语义：基于框架 `parse_llm_json_object(require_key="done")` 提取含 done 键的对象，兼容 markdown fence、prose 包裹、字符串内裸控制字符、尾逗号，格式示例在前、真实结果在后时取最后一个含 done 对象，done 支持字符串与数值归一化） | — |
| `delivery_provenance.py` | 核心 | Human 前缀投递横幅：`format_delivery_banner`、`prepend_plain_banner`、`ingress_from_channel_metadata`、`apply_delivery_banner`、`resolve_general_agent_pipeline_labels`（含 `web_chat`→http_gui/browser_sse、`cron`、`eval`、**`headless_wakeup`→async_wake_consumer** 等）、`apply_general_agent_pipeline_banner`；多模态首块合并且幂等 | ✅ I/O/P 见文件头 |
| `session_id.py` | 核心 | `is_safe_session_id`：session_id/chat_id 文件路径插值的统一白名单校验（`[A-Za-z0-9:_-]`），拒绝 `..`/反斜杠/空字节等路径逃逸 | ✅ |
| `lock.py` | 核心 | `StandaloneLockProvider`/`MemoryAsyncLockProvider`：进程内 per-key 异步锁（SQLite、Skills、Cron 共享资源互斥） | ✅ |
| `git_worktree.py` | 核心 | 共享 git worktree 命令基础设施（kanban/sandbox 共用一份，避免语义漂移）：`_GIT_ENV`（C-locale env）、per-base_dir merge 锁 `_get_merge_lock`、`_git_identity`（repo 无 user 配置时仅注入缺失的 `user.name/user.email`）、`_auto_commit_dirty_worktree`、`_collect_conflict_files`、`_abort_merge`（失败时 warning 日志，防 MERGE_HEAD 静默残留）、`_worktree_is_dirty`（fail-closed）与 worktree 业务错误类型 `WorktreeErrorReason`/`WorktreeCreateError`/`_classify_git_error` | ✅ |
| `ui_data_merge.py` | 辅助 | `deep_merge_ui_data`：A2UI binding dict 深合并（stream collector + chat UI artifact DB patch 共用） | ✅ |
| `__init__.py` | 核心 | 模块入口，公共 API 导出 | — |

---

## 依赖关系

- **内部**：`fastapi`、`PIL`、`langchain_core`、`app/schemas`（responses）
- **被依赖**：`app/api/`、`app/services/`、`app/ai_agents/`、`app/core/*`
