# api/chats/chat/

## 架构概述

单会话消息与流式子路由。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 挂载子路由；**优先**挂载 `../test_fixtures`（E2E seed 路由） | ✅ |
| `catchup.py` | 模块 | Get catchup briefs for all chats with unread activity. | ✅ |
| `compaction.py` | 模块 | 压缩摘要、归档只读、context pins/branches CRUD、snapshot bookmark fork | ✅ |
| `copilot.py` | 模块 | Co-Pilot API：run-digest GET、advisor ask/messages/clear | ✅ |
| `core.py` | 模块 | 会话 CRUD 核心：列表（分页/来源/项目过滤）、元数据、`GET /recall/search`（@chat SSOT）、`GET /recall/entries`、创建/更新、Fission 拓扑、session-skills PATCH、active-moa-preset PATCH、session-access-roots grant POST / revoke PATCH；PATCH workspace 在 project 已绑定时 409 | ✅ |
| `fork.py` | 模块 | Fork conversation from specific message index. | ✅ |
| `rewind.py` | 模块 | Rewind conversation to before a user message; optional `scope` (conversation/files/both) reverts file snapshots and returns reverted-file details. | ✅ |
| `handoff.py` | 模块 | Web→Channel handoff API. | ✅ |
| `messages.py` | 模块 | Message search (FTS5), paginated loading, focus-flush, export (metadata + messages + agentInfo + toolCallDetails + usageSummary + toolSummary). | ✅ |
| `export_helpers.py` | 模块 | Chat export 数据载荷聚合（工具统计/工具详情/智能体元数据）与凭据脱敏。 | ✅ |
| `sandbox.py` | 模块 | Chat sandbox session management (enable/disable/merge/status/diff). Git worktree isolation for agent experimentation. `disable` explicitly discards the sandbox worktree (force-remove even when dirty). `merge` rolls the merge back on conflict (abort) and reports the conflicting file count. | ✅ |
| `title.py` | 模块 | if not chat_id.strip(): | ✅ |
| `trash.py` | 模块 | Chat trash (recycle bin) API endpoints. | ✅ |
| `share.py` | 模块 | Conversation share API：创建/撤销/状态查询时间受限只读公开链接（支持可选密码）；**撤销为 per-token 语义**：create 持久化活跃 token 指纹（`share_token_fingerprint`）+ 展示元数据（`share_token_expires_at`/`share_token_protected`），revoke 把活跃指纹移入 `share_revoked_fingerprints` 集合，重新分享仅清 chat 级标记、集合保留，因此**撤销过的链接永不复活**（未撤销的既有链接继续有效至各自 TTL）；**`GET /{chat_id}/share` 状态查询四态**：unshared（从未分享或链接已过期——**过期（无论是否密码保护）一律视为 unshared**）/ revoked（优先判断，stale 展示元数据不影响）/ active（无密码用持久化 exp 经 `share_token.rebuild_chat_share_token` 确定性重建链接，对齐 artifact rebuild 先例）/ password_protected（密码 token 不重建——重建会产生无密码版本绕过密码门，仅返回状态）；公开页（`/public/chat-share/{token}`，GET+POST）密码门表单 **POST body 提交（CWE-598：密码不进 URL）**，解锁成功 **303 See Other PRG** 重定向 + 短时 HMAC unlock cookie（刷新/重访免密，credential 签发/解析共用 `core.security.share_unlock`，安全参数单点维护；临近过期 <60s 无法签发 cookie 时直接返回内容防回弹），GET 兼容旧 `?p=` query；**生命周期状态在密码门之前退休**：token payload 为 base64（仅 HMAC 签名需密码），`_decode_share_claims_unverified` 解码 cid 预查聊天，已撤销/已删除的分享在门之前先 404「Link Revoked」/「Content Unavailable」——死链对未解锁访客绝不呈现密码门；**分享内容页响应统一共享隐私头 `X-Robots-Tag: noindex, nofollow` + `Cache-Control: no-store` + `Referrer-Policy: no-referrer`（`core.security.share_headers` 单点，防搜索引擎收录 + 撤销后浏览器/CDN 缓存不可绕过 + token 型 URL 不泄露给三方）**；**失效/过期/已撤销/内容不可用统一走 `core.security.share_status_page::share_not_found`：浏览器（Accept 含 text/html）返回自包含 HTML 失效页（Link Expired / Link Revoked / Content Unavailable），API 客户端返回 JSON 404**；分享 URL 基于 `core.infra.ingress::resolve_share_url_base` 共享公网 base（artifact 双端复用，云托管/隧道可外网访问，无 ingress 降级请求 origin，本地/桌面可用）；cloud 用 public URL，local/desktop 前端回退客户端 HTML export | ✅ |
| `turn.py` | 模块 | Turn lifecycle: retry, regenerate, sibling switch, truncate-after (edit-resend), undo, rewind. | ✅ |
| `trajectory.py` | 模块 | `GET /{chat_id}/trajectory` — 抽取多轮执行轨迹（包含 tool_calls、参数、耗时、Token 与错误分类），供前端跨会话时序瀑布流与双轨 Diff 对比消费。 | ✅ |
| `replay.py` | 模块 | `POST /{chat_id}/replay` — 会话重放与确定性验证接口，计算工具调用序列对齐率、Jaccard指数与确定性得分（0.0 ~ 1.0）。 | ✅ |
| `memory_extract.py` | 模块 | `POST /{chat_id}/memory/retry-extract` — 对最近一轮 user/assistant 重新调度 memory extract；incognito / 无效 turn → 400；chat 不存在 → 404；返回 `scheduled` / `already_in_flight` | ✅ |
