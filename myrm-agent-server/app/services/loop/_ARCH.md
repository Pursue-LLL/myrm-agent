# app/services/loop 模块架构

会话级定时循环调度业务域。提供会话定时触发、自适应退避与动态状态分发，并与用户输入仲裁协同保障并发安全。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 基础 | 导出 `SessionLoopManager`、`SessionTurnArbiter` 及相关 DTO | ✅ |
| `session_loop_manager.py` | 核心 | 会话循环生命周期管理器，处理循环启动、停止、Tick 调度与自适应退避 | ✅ |
| `session_loop_types.py` | 核心 | 会话循环状态 DTO 与启动结果封装，服务于 REST 及 SSE 状态推送 | ✅ |
| `session_turn_arbiter.py` | 核心 | 会话轮次优先级仲裁器（单例模式），用户交互绝对优先并延迟循环唤醒，避免 409 锁冲突 | ✅ |
