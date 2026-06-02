
# app/api/cron/routes 模块架构

Cron 子路由集。按功能域拆分定时任务 API 端点，统一挂载到 `/cron/` 前缀下。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `jobs.py` | 核心 | Cron Job CRUD 端点 | ✅ |
| `runs.py` | 核心 | 运行历史查询端点 | ✅ |
| `triggers.py` | 核心 | 触发调度和完整性验证端点 | ✅ |
| `heartbeat.py` | 辅助 | 心跳 REST 端点 | ✅ |
| `push_messages.py` | 辅助 | Push 消息端点 | ⚠️ 待补 |
| `stats.py` | 辅助 | Token 用量统计端点 | ✅ |
| `helpers.py` | 辅助 | 转换工具和 manager 访问器 | ⚠️ 待补 |
