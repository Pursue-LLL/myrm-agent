# api/channels/connection_probes/

## 架构概述

渠道设置页「测试连接」背后的凭据探测：每个探测用表单里的凭据真实调用对应服务，回答凭据是否可用。失败文本经 `safe_err_msg` 脱敏后才返回（服务的报错里可能带着用户刚填的令牌或密码）。包门面导出 `router` 与 `safe_err_msg`，由 [../test_connections.py](../test_connections.py) 挂载。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包门面：导出 `router` 与 `safe_err_msg` | ✅ |
| `bot_platforms.py` | 模块 | 飞书、钉钉、Slack、Discord、企业微信、Teams、Matrix、Telegram、Google Chat、QQ 的 `POST /{platform}/test` 探测；各平台客户端在处理函数内导入，只有点「测试」时才加载 | ✅ |
| `error_text.py` | 模块 | `safe_err_msg`：探测失败文本的凭据脱敏，所有探测（含 `test_connections.py` 里的）共用 | ✅ |
