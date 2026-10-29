# api/integrations/oauth/

## 架构概述

OAuth 连接的 HTTP 层：个人凭证的加密存取、MCP 与 Google Workspace 的授权码 + PKCE 流程、xAI 设备码登录、模型供应商订阅登录的状态与断开，以及授权结束后回给浏览器的结果页。各模块各自导出一个 `router`，由 [../router.py](../router.py) 按下表的前缀挂载（挂载顺序决定同前缀下的匹配顺序，改动时保持不变）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 路由前缀

| 模块 | 前缀（相对 `/integrations`） |
|------|------|
| `credentials.py` | `/oauth` |
| `mcp.py` | `/mcp/oauth` |
| `google_workspace.py` | `/google-workspace/oauth` |
| `xai.py` | `/xai/oauth` |
| `provider.py` | `/provider-oauth` |

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包标记，不重导出；路由在 `../router.py` 挂载 | ✅ |
| `credentials.py` | 模块 | OAuth 凭证管理 API。提供个人 SaaS 集成凭证的加密存储、查询和撤销，支持断开时可选清除同步数据；列表项带 `renewable`（访问令牌可自行续期）与 `needs_reauth`（供应商已永久拒绝刷新令牌），只读已存凭证与进程内失败记忆、不发起网络请求。 | ✅ |
| `mcp.py` | 模块 | MCP OAuth 2.0 + PKCE authorization flow API；回调结果页经 `result_page`；提供方回传的错误描述转义后显示，错误码只写日志。 | ✅ |
| `google_workspace.py` | 模块 | Google Workspace OAuth 2.0 + PKCE；readonly/write tier；写入 oauthCredentials（不含 client_secret）；回调结果页经 `result_page` | ✅ |
| `google_workspace_flow.py` | 模块 | OAuth PKCE 会话态、scope tier、redirect 解析与 Google userinfo 辅助 | ✅ |
| `xai.py` | 模块 | xAI OAuth device-code 登录（仅 `/start`、`/poll`）；SuperGrok 订阅授权；`/poll` 把 RFC 8628 的 `slow_down` / `expired_token` / `access_denied` 映射为客户端据以行动的 `pending` / `expired` / `denied`；待完成的流程只存在于本进程内存，进程不持有该流程时 `/poll` 返回 404；复用 oauth_store 持久化 | ✅ |
| `provider.py` | 模块 | Provider OAuth 状态与断开（仅 xAI SuperGrok）：`/status/{provider}`、`/disconnect/{provider}` 供模型页、凭证页与启动期登录标记校准共用（设备码登录在 `xai.py`）；`/test/seed-oauth`、`/test/cleanup-oauth` 仅本地模式供 Chrome E2E；OAuth token 经 `config_loader` 注入 model_resolver 链路 | ✅ |
| `result_page.py` | 页面 | OAuth 回调结果页的唯一出口：`OAuthOutcome`（成功 / 被拒 / 失效 / 失败 / 连不上）对应一页中英双语内容，提供方回传的错误描述转义后才显示，错误码、网络异常与内部错误只进日志；浅 / 深色对比度由 `tests/api/integrations/oauth/test_result_page.py` 钉住 | ✅ |

## 模块依赖

- 凭证持久化：`app.services.integrations.oauth_store`（加密的 `oauthCredentials`）、`app.services.agent.oauth_refresher` 与 `oauth_token_policy`（续期与失败记忆）。
- 授权码流程的回调页只经 `result_page` 输出；`google_workspace_flow` 只被 `google_workspace` 使用。
- 测试镜像在 `tests/api/integrations/oauth/`；回调页的对比度由 `tests/architecture/test_html_pages_contrast_gate.py` 登记。
