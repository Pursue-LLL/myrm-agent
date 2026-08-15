# services/memory/ledger 模块架构

## 架构概述

单用户记忆操作账本。持久化记忆事件、健康快照缓存和外部记忆导入来源；`record_event` 统一保证事件发布发生在持久化成功之后——杜绝 ghost event；配套 Guardian 调度策略（运行窗口判定）与晨间摘要按维护窗口聚合读取、守卫不可用告警聚合快照。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `operation_ledger.py` | 核心 | 单用户记忆操作账本服务。持久化记忆事件、健康快照缓存和外部记忆导入来源；`record_event` 统一保证事件发布发生在持久化成功之后（`commit=True` 落库后立即发布，`commit=False` 经 after_commit 延迟到调用方事务成功提交，回滚则丢弃）——杜绝 ghost event；提供 `list_events_for_session` 供 Session Replay memory_events 叠加查询；`list_diagnostic_events` 按 source/target 约定检索诊断审计事件供历史趋势；metadata 列支持嵌套 JSON（标量 SSE 收缩与嵌套趋势反投影并存） | ✅ |
| `operation_ledger_guardian.py` | 辅助 | Guardian 晨间摘要按维护窗口聚合读取与守卫不可用告警聚合快照（按 frequency tier 自适应最小事件阈值 + escalation 阈值元数据） | ✅ |
| `guardian_policy.py` | 核心 | Memory Guardian 调度策略服务。持久化 `frequency_tier`/`quiet_window` 配置，提供运行窗口判定与下次窗口开启时间计算，并记录 `timezone_source`；首访时完成浏览器时区初始化，无浏览器时区头时由 API 使用服务端本地时区兜底，后续收到真实客户端时区头时可自动纠偏 | ✅ |
