# api/chats/chat/share/

## 架构概述

会话分享子包：时间受限的只读公开链接（支持可选密码）。上级文档：[../_ARCH.md](../_ARCH.md)。由单文件 `share.py` 拆分而来（纯搬迁，行为不变）：管理端路由与公开页路由各自成文件，互不依赖；`__init__.py` 为聚合门面，`from .share import router` 挂到会话路由，`public_router` 由 `app/api/router.py` 以 `/public/chat-share` 单独挂载（免鉴权）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `router`（管理端）与 `public_router`（公开页） | ✅ |
| `manage.py` | 模块 | 管理端：创建/撤销/状态查询。**撤销为 per-token 语义**：create 持久化活跃 token 指纹（`share_token_fingerprint`）+ 展示元数据（`share_token_expires_at`/`share_token_protected`），revoke 把活跃指纹移入 `share_revoked_fingerprints` 集合，create 也把它所替换的旧链接指纹移入同一集合（一个会话同一时刻只有一条有效链接；同一秒内同参数重复创建得到的是同一个 token，不算被替换），重新分享仅清 chat 级标记、集合保留，因此撤销过或被替换的链接永不复活；**`GET /{chat_id}/share` 状态四态**：unshared（从未分享或链接已过期——过期无论是否密码保护一律视为 unshared）/ revoked（优先判断）/ active（无密码用持久化 exp 经 `rebuild_chat_share_token` 确定性重建链接）/ password_protected（密码 token 不重建，重建会产生无密码版本绕过密码门，仅返回状态）；分享 URL 基于 `core.infra.ingress::resolve_share_url_base`（云托管/隧道可外网访问，无 ingress 降级请求 origin） | ✅ |
| `public.py` | 模块 | 公开页（`/public/chat-share/{token}`，GET+POST，免鉴权）：密码门表单 **POST body 提交（CWE-598：密码不进 URL）**，解锁成功 303 See Other PRG + 短时 HMAC unlock cookie（临近过期 <60s 无法签发 cookie 时直接返回内容防回弹），GET 也接受 `?p=` 查询参数；**生命周期状态在密码门之前退休**：`_decode_share_claims_unverified` 解码 cid 预查聊天，已撤销/已删除先 404，死链对未解锁访客绝不呈现密码门；错误密码按分享 + 客户端地址计数，5 次后 5 分钟内 429（含 `Retry-After`，持有解锁 cookie 的访客不受影响，见 `core/security/share/share_attempt_guard.py`；锁定生效的那一次经 `services/audit/lockout_events.py` 上报一次）；内容页按访客 `Accept-Language` 以中/英文渲染（`resolve_share_lang`），响应统一带共享隐私头（noindex/nofollow + no-store + no-referrer）；失效/过期/已撤销/内容不可用统一走 `share_not_found`（浏览器得按 `Accept-Language` 中英文的 HTML 状态页，API 客户端得英文 JSON 404）；门禁页与锁定页同样按访客语言 | ✅ |
