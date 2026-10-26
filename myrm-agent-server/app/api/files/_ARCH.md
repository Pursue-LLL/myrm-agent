# api/files/

## 架构概述

文件上传、下载与 artifact 分享 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Files management API module | ✅ |
| `evicted.py` | 模块 | UECD evicted-file read API (`GET /evicted` paginated line-range); harness `read_evicted_line_range`; default `limit=500`; path traversal checks; missing file → HTTP 404 + `{"expired": true}` | ✅ |
| `artifact_api.py` | 模块 | List/retrieve/verify artifacts；`GET /files/artifacts` 支持可选 `limit`、`project_id` 与 `assessment_import_candidate` 查询参数（候选控量 + 项目相关候选过滤 + 评估导入资格语义探测：内容可解析性 + ledger 已导入检查，返回 `assessment_import_candidate.{status,reason}`，status 含 `importable/not_importable/already_imported/unknown`）；exposes `publications[]` per artifact；`POST /download-bundle` packages multiple artifacts into a single ZIP archive；每个 artifact 的 vault 对象按其所属会话的工作区（`resolve_chat_workspace_root`）读取，不看进程目录 | ✅ |
| `provenance_api.py` | 模块 | Artifact Provenance Hub & Cross-Session Asset Retriever API (`GET /provenance`, `GET /provenance/{id}`); multi-category asset classification (document/code/data/media/link/other), category stats, and bidirectional session provenance linking；各会话产物大小按该会话工作区里的 vault 读取。 | ✅ |
| `artifact_share_api.py` | 模块 | Lets GUI users share html/pdf/document artifacts without publication deploy；支持活跃链接列表（`GET /shares`，无密码链接按需重建 share_path，密码链接返回 register 时持久化的 share_path，两类链接均可复制/打开）、手动撤销（`DELETE /shares/{record_id}`，幂等 204/404，撤销写入审计日志）与撤销后公开入口 404（revoked_at 前置校验 + 拒绝重新 materialize），登记走 `services.artifacts.share_registry`；create/list 响应携带 `share_url`（基于共享 public-ingress 分享 base `resolve_share_url_base` 的绝对链接，chat/artifact 双端复用，托管/隧道部署可达，无 ingress 时降级为 `None` 由前端按 origin 组装） | ✅ |
| `artifact_share_public.py` | 模块 | 免认证公开入口（`/public/artifact-share/{token}`）三路由（GET+POST）：入口/尾斜杠索引/静态资源；多文件 bundle GET 307 尾斜杠跳转；密码保护走 HMAC unlock cookie（credential 签发/解析共用 `core.security.share_unlock`，安全参数单点维护），密码门表单 **POST body 提交（CWE-598：密码不进 URL）**，解锁成功 **303 See Other PRG** 重定向到干净 GET URL（分享临近过期 <60s 无法签发 cookie 时 POST 直接返回内容，避免 303 回弹死循环），旧 `?p=` 链接仍兼容；CSP/nosniff/DENY 安全头（仅 HTML）；所有文件统一共享隐私头 `X-Robots-Tag: noindex, nofollow` + `Cache-Control: no-store` + `Referrer-Policy: no-referrer`（`core.security.share_headers` 单点，防搜索引擎收录 + 撤销后即时生效 + token 型 URL 不泄露给三方）；**失效/过期/已撤销/内容不可用统一走 `core.security.share_status_page::share_not_found`：浏览器（Accept 含 text/html）返回自包含 HTML 失效页，API 客户端返回 JSON 404**；撤销检查在认证前（已撤销链接包括密码链接直接 404，不展示密码框）；限流 30/60 | ✅ |
| `browse.py` | 模块 | Workspace browse API; `chat_id` 分支经 `effective_workspace` SSOT；`/browse/search` uses harness `filesystem_suggest`；`/browse/content` 文本内联 1MB 截断 + 二进制 FileResponse 全量流式（MIME + Range）；`FileEntry.is_text` 权威判定 + Content-Disposition RFC 5987 转义 | ✅ |
| `browse_watch.py` | 模块 | POST/DELETE `/browse/watch` — refcounted vault watch → `WORKSPACE_FILE_CHANGED` SSE. | ✅ |
| `hosting_api.py` | 模块 | Multi-target artifact publish, hosting targets CRUD, publications | ✅ |
| `document_extract.py` | 模块 | Document content extraction API. | ✅ |
| `local_actions.py` | 模块 | Local-only file reveal/open endpoints（单文件 `POST /files/{id}/reveal`、会话产物目录 `POST /files/chats/{chat_id}/reveal`，依赖 `reveal_utils`）；`sandboxes/<chat_id>/…` 路径与产物目录都落在该会话的工作区内，产物目录只在 vault 里真有最新版本对象时才算存在 | ✅ |
| `pdf_extract.py` | 模块 | PDF content extraction API endpoint；沙箱/云模式下页图落盘，来源标记取自 `core.storage.chat_bound.pdf_extract_source`，随绑定上传一起清理。响应统一走 camelCase：声明字段由 `alias_generator=to_camel` 负责，`image_trace` 是裸字典、由 `field_serializer` 逐键转换（含 `truncated`），`PDFImageItem` 自带同一 `model_config`，否则前端读 `mimeType` / `fileUrl` / `droppedCount` 会静默落空。三个投递缺口各有字段：`truncated` 表示「整页投递下内嵌图版被上限截断」，`parsedPages < pageCount` 表示投递窗口截断，`pagesWithoutText` 逐页列出文本层读不到的页（扫描/空白），三者不互相代替；`PDFImageItem.pageNumber` 让前端区分「哪些扫描页真被当图发出」与「超出图版上限而未发出的页」 | ✅ |
| `revert.py` | 模块 | File revert & review API — exposes `revertible`/`skip_reason` on changes; hydrate/cleanup via `revert_hydrate`; Agent notify via `revert_agent_notify`. | ✅ |
| `router.py` | 路由 | Files API router | ✅ |
| `storage.py` | 模块 | 文件管理 API | ✅ |
| `suggest.py` | 模块 | `@` reference suggestion API — workspace via `effective_workspace` SSOT; uploaded/generated/wiki via harness + services；带 `source_chat_id` 的文件（会话内生成的、无痕会话上传的）只在该会话的建议里出现 | ✅ |
| `upload.py` | 模块 | 文件上传 API；可选表单字段 `chat_id`（仅无痕会话由前端传入）把上传绑定到该会话，绑定的文件随会话清理、不进导出（见 `core/storage/_ARCH.md`） | ✅ |
| `vault_api.py` | 模块 | Retrieve the raw binary/text content of a vault object；对象所在工作区由可选 `chat_id` 指定，缺省时按指向它的 artifact 所属会话定位，都没有才回退进程工作区 | ✅ |
| `vault_proxy.py` | 模块 | Vault secure artifact proxy router. | ✅ |
| `workspace_ops.py` | 模块 | Workspace file write operations API（上传/mkdir/重命名/移动/删除）；`resolve_workspace` / `validate_target` / `dedup_filename` 是工作区边界、危险路径、敏感文件守卫与重名规则的唯一出处，`workspace_text.py` 复用 | ✅ |
| `workspace_text.py` | 模块 | 工作区文本编辑 API：`GET /browse/text`（内容 + sha256 版本 + 可编辑判定/只读原因）、`PUT /browse/text`（`base_version` 比对后保存，冲突 409、无无条件写路径）、`POST /browse/text/copy`（排他创建同目录副本）；正文走 `content_b64`，避免请求文本净化改写文件内容；所有拒绝都带 `reason` 明细（`version_conflict` / `write_blocked` / `binary` / `not_utf8` / `mixed_line_endings` / `too_large` / …）供前端本地化，**不使用 403/423**（前端 api 层会据此跳登录/弹锁屏） | ✅ |
| `organize.py` | 模块 | Workspace organize HITL API — apply/rollback（含 `jobStatus`）/ latest-job | ✅ |
