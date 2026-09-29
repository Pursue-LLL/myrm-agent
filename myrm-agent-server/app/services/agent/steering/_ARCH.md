# steering 域

会话级 steering 聚合出口。管理运行中会话的 SteeringToken 注册与显式 opt-in 政策注入（去重/上限/侧信道信封/计数器）。

| 文件   | 职责                                                     |
| ------ | -------------------------------------------------------- |
| `__init__.py` | 域唯一入口 — 重导出 registry 与 policy |
| `registry.py` | 会话级 SteeringToken 注册表（chat_id → 运行中 token，10s 短缓冲对账） |
| `policy.py`   | 政策模式 — 每会话 harness 引用队列，经 `drain_into_token` 注入存活 token；直连语义零改动 |
