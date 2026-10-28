# services/audit/

## 概述

平台与认证审计日志读取（JSONL，供 Security Center 与 admin API 复用）及暴力破解锁定的上报。

## 文件

| 文件 | 职责 |
|------|------|
| `auth_log_reader.py` | 读取本地 `auth_audit.jsonl`，序列化为 API 事件字典 |
| `lockout_events.py` | 暴力破解锁定上报：锁定生效的瞬间（非每次被拒请求，攻击期间不会刷屏）记一条 WARNING，并在启用认证审计的部署（sandbox / 远程 WebUI）写 `rate_limit_exceeded` 审计事件；只记客户端地址、范围（分享密码门 / WebUI 登录）与分享令牌指纹前 12 位，不含密码或可用令牌 |

## 依赖

- `app/services/security/platform_audit.py` — sandbox 走 CP internal，local 走本模块；其 `rate_limited` 分支的事件由 `lockout_events.py` 产生
- `lockout_events.py` 的调用方：公开分享路由（聊天 / 工件）的密码门、`app/services/webui/auth_service.py` 的登录失败
