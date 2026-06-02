# api/health 模块架构


## 架构概述

健康检查与诊断 API。提供 liveness/readiness probe、系统信息、metrics 端点，以及聚合底座 Harness 框架与业务层的全局 `doctor` 诊断体系，
支持容器编排（K8s）、运维监控和实时告警。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包初始化 | — |
| `router.py` | 核心 | 健康检查（liveness/readiness/info/metrics/doctor/repair-actions 等端点）, SSE 健康告警推送 | 核心业务 |
| `diagnostic.py` | 辅助 | 诊断端点（获取底层引擎的安全加固 DiagnosticStatus） | 辅助状态 |
| `benchmark.py` | 核心 | 性能基准测试异步端点（POST /benchmark）及 SSE 进度推送 | 性能诊断 |
| `memory.py` | 核心 | 内存诊断与 Conversation Recall 索引健康端点；`/memory/conversation-recall` 仅返回计数、缺口和 FTS 状态，不暴露会话文本 | 核心业务 |

## `/metrics` 端点架构

暴露给 Control Plane 的系统级监控指标：
- **dlq**: 死信队列堆积量和状态（healthy/degraded/unhealthy）
- **memory_pressure**: 内存压力等级（NORMAL/WARNING/CRITICAL/EMERGENCY）和使用率百分比。数据来源于 Harness `MemoryPressureMonitor`，通过 `monitors.py` 生命周期管理。

## `/doctor` 端点架构

### 数据流
```
Harness Framework Layer
  ├─ check_network_health (DNS/TLS)
  ├─ check_workspace_storage_health (Storage + SQLite WAL)
  ├─ check_database_health (SQLite 连接)
  ├─ check_qdrant_health (Qdrant 连接)
  ├─ check_system_resources (CPU/Memory 资源)
  └─ get_terminal_errors (AgentEngine)
           ↓
Server Business Layer
  └─ check_dlq_health (DLQ 堆积检测)
           ↓
Aggregated Response
  {
    "harness": [HealthReport, ...],  // message + detail + fix_suggestion
    "server": [HealthReport, ...],
    "repair_actions": [RepairAction, ...]
  }
           ↓
SSE Event Bus (on fail/warn)
  → AppEventType.HEALTH_ALERT (includes message, detail, fix_suggestion)
           ↓
Frontend DoctorDashboard
  ├─ Grouped Display (Harness/Server)
  ├─ message (primary) + detail (monospace secondary)
  ├─ Overall Health Score (0-100%)
  ├─ Search & Filter
  ├─ Health Trend Chart (24h history, detail in modal)
  └─ Toast Notification (SSE, message only)
```

### 分层原则
- **Harness 层**: 检查框架基础设施的**连接性** (服务是否可达)
- **Server 层**: 检查业务特有功能的**完整性** (DLQ、Channel、Webhook 等)
- **Repair 层**: 只生成和执行白名单修复动作；禁止任意 SQL、任意 shell、任意文件删除

## `/repair-actions/{action_id}/execute` 端点架构

执行 GUI 确认后的白名单修复动作。当前仅允许枚举动作，客户端不能提交任意命令、SQL 或路径。

- `dry_run=true`: 预览影响，不修改运行时状态
- `confirm=true`: 执行状态变更动作时必须显式确认
- 审计与审批入口复用业务层 approval/事件体系，不在 Harness 中执行修复

### 实时告警机制
当检测到 `fail` 或 `warn` 状态时:
1. `/doctor` API 自动发布 `AppEvent` (类型: `HEALTH_ALERT`)
2. EventBus 通过 SSE 推送给所有订阅的前端客户端
3. 前端 Toast 通知用户立即响应

### 性能特性
- 并发执行所有探针 (Harness 层通过 asyncio.gather)
- 超时保护: 每个探针最多 5 秒超时
- 前端 30 秒轮询 + SSE 实时推送

## `/history` 端点架构

### 数据流
```
Background Recorder (every 3 min)
  ├─ Fetch current health from /doctor
  ├─ Calculate overall_score (pass_count / total * 100)
  ├─ Determine overall_status (fail > 0 = fail, score < 80 = warn, else = pass)
  ├─ Store to SQLite (system_health_history table)
  └─ Auto-cleanup (delete records > 7 days old)
           ↓
Frontend API Request (/api/v1/health/history?hours=24)
  ├─ Query SQLite (timestamp >= cutoff)
  ├─ If table missing (migrations not applied): HTTP 200 + `{"data":[]}` (no 500)
  ├─ Return time-series data
  └─ Frontend HealthTrendChart (Recharts line chart)
```

### 数据存储
- **表**: `system_health_history`
- **字段**:
  - `timestamp`: 采样时间
  - `overall_status`: pass/warn/fail
  - `overall_score`: 0-100分
  - `component_reports`: JSON (完整探针报告)
- **采样频率**: 3分钟
- **保留期**: 7天

### 查询参数
- `hours`: 查询最近N小时数据 (默认24, 范围1-168)

### 前端组件
- **HealthTrendChart.tsx**: Recharts折线图
  - 每3分钟刷新数据
  - 自动颜色编码 (fail=红, warn=黄, pass=绿)
  - 鼠标悬停显示详细信息
  - **时间范围选择**: 24h/7d/30d下拉框
  - **点击查看详情**: 点击数据点弹出Modal展示component_reports (分Harness/Server层)
