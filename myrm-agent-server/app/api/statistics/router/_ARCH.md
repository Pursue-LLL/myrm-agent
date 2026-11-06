# app/api/statistics/router 子包架构

统计 API 的基础路由。按端点域分模块，共享一个 `APIRouter`；`app.api.statistics.router` 导入路径不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 `router` 与 `settings`：先导入端点模块注册路由，再挂载 session / timeline / radar 等子路由 | — |
| `common.py` | 辅助 | 共享 `APIRouter` 与 logger | ✅ |
| `usage.py` | 核心 | usage 统计、雷达、按天/按会话用量 | ✅ |
| `tools.py` | 核心 | 工具稳定性与 Agent 工具健康 | ✅ |
| `activity.py` | 核心 | 全局活跃模式、Top 会话与导航徽标 | ✅ |

## 依赖关系

- 上游：`app.api.statistics.usage_aggregation`、`app.config.settings`、`app.database.*`、harness `EventLogAnalytics`
- 下游：`app/api/statistics/__init__.py`（把 `router` 挂到统计入口）
