# utils 模块架构


---

## 架构概述

业务特有工具函数模块，提供错误处理、响应格式化、文件操作、聊天格式转换、图片压缩等核心能力。是整个系统的通用工具层，被各模块广泛使用。专注通用性和可复用性。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|-----|------|------|-------|
| `errors/` | 核心 | API 错误工具，按职责分 6 个模块（constants / base / http / handlers / redaction / llm）：`MyrmError` 与业务码分类、`StandardHTTPException` 与 HTTP 错误工厂、FastAPI 异常处理器、home 路径折叠与 payload 脱敏、LLM 异常归一。见 [errors/_ARCH.md](errors/_ARCH.md) | ✅ |
| `response_utils.py` | 核心 | `success_response`、`list_response`、`paginated_response` | — |
| `files_utils.py` | 核心 | `extract_file_id_from_url`、`read_image_bytes`（存储 URL → 图片原始字节与 MIME，只读本地存储不发网络请求）、`read_image_as_base64`（同上的 base64 形式），均通过 FilesService + StorageProvider 统一存储访问 | — |
| `media_file_reader.py` | 核心 | `read_uploaded_media_file_content`：为 harness `FileContentReader` 注入 `/api/media/files/{id}/content` 字节（VisionFallback + MediaResolver） | — |
| `chat_utils/` | 子包 | 聊天工具：`history`（`convert_chat_history` 前端 → LangChain、`parse_judge_json`）、`images`（旧图降级 / base64 压缩）、`multimodal`（`preprocess_inbound_multimodal_query` + `_process_human_content`）、`image_items` / `video_items`（单条内容转换）。见 [chat_utils/_ARCH.md](chat_utils/_ARCH.md) | ✅ |
| `delivery_provenance.py` | 核心 | Human 前缀投递横幅：`format_delivery_banner`、`prepend_plain_banner`、`ingress_from_channel_metadata`、`apply_delivery_banner`、`resolve_general_agent_pipeline_labels`（含 `web_chat`→http_gui/browser_sse、`cron`、`eval`、**`headless_wakeup`→async_wake_consumer** 等）、`apply_general_agent_pipeline_banner`；多模态首块合并且幂等；横幅经 `skill_invocation.decorate_behind_skill_tag` 落在开头的 `[use skill]` 标签之后 | ✅ I/O/P 见文件头 |
| `skill_invocation.py` | 核心 | `decorate_behind_skill_tag`：宿主在用户文本前加内容（投递横幅、回复上下文）或替换用户文本（超大载荷落盘后的引用块）时，让开头的 `[use skill]` 标签保持在最前（harness 只认位于文本最开头的标签，否则显式调用技能与其钩子静默失效） | ✅ I/O/P 见文件头 |
| `session_id.py` | 核心 | `is_safe_session_id`：session_id/chat_id 文件路径插值的统一白名单校验（`[A-Za-z0-9:_-]`），拒绝 `..`/反斜杠/空字节等路径逃逸 | ✅ |
| `git_worktree.py` | 核心 | 共享 git worktree 命令基础设施（kanban 任务的工作树生命周期使用）：`_GIT_ENV`（C-locale env，并入 harness 的 `HARDENED_GIT_ENV`：凭据请求直接失败而不是等终端输入）、`_run_git`（碰工作树或更新引用的 git 命令唯一入口，经 harness `hardened_git_argv_async` 加固：仓库自带的钩子、过滤器、合并驱动、签名程序与联网传输都不会运行，加固不了则抛 `GitHardeningError`）、per-base_dir merge 锁 `_get_merge_lock`、`_git_identity`（repo 无 user 配置时仅返回缺失的 `user.name=`/`user.email=` 项，经 `-c` 注入）、`_ensure_worktree_excluded`（worktree 目录写入 `.git/info/exclude`）、`_git_worktree_add`（`git worktree add --force -B` 创建）、`_auto_commit_dirty_worktree`、`_merge_branch_into_current`（identity 兜底 + merge 失败自动 abort/收集冲突文件）、`_collect_conflict_files`、`_abort_merge`（失败时 warning 日志，防 MERGE_HEAD 静默残留）、`_worktree_is_dirty`（fail-closed）、`_remove_worktree`（`git worktree remove --force`）、`_delete_git_branch`（经 `_run_git` 删除分支：删除引用会触发仓库自带的 `reference-transaction` 钩子，加固后不运行；`merged_only` 时只删已合并的分支，未合并的提交保留）与 worktree 业务错误类型 `WorktreeErrorReason`（含 `UNSAFE_REPOSITORY`：仓库配置无法安全中和而被拒绝，`_git_worktree_add` 与 worktree 服务据此区分于普通 git 失败）/`WorktreeCreateError`/`_classify_git_error` | ✅ |
| `__init__.py` | 核心 | 模块入口，公共 API 导出 | — |

---

## 依赖关系

- **内部**：`fastapi`、`PIL`、`langchain_core`、`app/schemas`（responses）
- **被依赖**：`app/api/`、`app/services/`、`app/ai_agents/`、`app/core/*`
