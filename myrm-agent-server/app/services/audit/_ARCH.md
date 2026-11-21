# services/audit/

## 概述

平台与认证审计日志读取（JSONL，供 Security Center 与 admin API 复用）、暴力破解锁定的上报，以及分享链接的创建与打开事件。

## 文件

| 文件 | 职责 |
|------|------|
| `auth_log_reader.py` | 读取本地 `auth_audit.jsonl`，序列化为 API 事件字典 |
| `lockout_events.py` | 暴力破解锁定上报：锁定生效的瞬间（非每次被拒请求，攻击期间不会刷屏）记一条 WARNING，并在启用认证审计的部署（sandbox / 远程 WebUI）写 `rate_limit_exceeded` 审计事件；只记客户端地址、范围（分享密码门 / WebUI 登录）与分享令牌的短指纹（`share_hmac.token_log_id`），不含密码或可用令牌 |
| `share_events.py` | 分享链接事件：创建时 `share_created`（kind、source = 分享对话框 / IM 按钮），打开时 `share_access`（kind、granted，或 denied + 原因：已撤销 / 已过期 / 内容或文件或会话不可用 / 错误密码）；各一条 INFO 日志，不建表、不建计数服务；链接只以令牌短指纹命名（`share_hmac.token_log_id`），入口页放行计一次（资源请求不计），每次错误密码计一次（锁定另由 `lockout_events` 上报），无法解码为我方令牌的拒绝不记（扫描器刷不动日志） |

## 依赖

- `app/services/security/platform_audit.py` — sandbox 走 CP internal，local 走本模块；其 `rate_limited` 分支的事件由 `lockout_events.py` 产生
- `lockout_events.py` 的调用方：公开分享路由（聊天 / 工件）的密码门、`app/services/webui/auth_service.py` 的登录失败
- `share_events.py` 的调用方：`services/artifacts/share/share_create.py` 与 `api/chats/chat/share/manage.py`（创建），公开分享路由（聊天 / 工件）的放行与拒绝
