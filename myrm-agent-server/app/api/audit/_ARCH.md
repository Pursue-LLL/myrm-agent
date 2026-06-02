# api/audit 模块架构


---

## 架构概述

认证审计日志查询 API 模块。

提供 Auth Audit Logs 的查询、统计和导出功能。
数据源：`.myrm/logs/auth_audit.jsonl`（由 `app/middleware/auth_audit.py` 在非回环认证时写入）。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `__init__.py` | ✅ 核心 | 包初始化 |
| `auth_router.py` | ✅ 核心 | Auth 审计日志 REST API：GET /logs（查询+过滤）、GET /stats（统计：成功/失败/Top IPs）、GET /export（CSV/JSON 导出）。JSONL 解析逐行容错，单行损坏不影响整体查询。 |
| `bash_router.py` | ✅ 核心 | Bash 命令审计 REST API：GET /logs（查询命令执行日志）、GET /stats（统计）、GET /export（CSV/JSON 导出）、POST /anomalies（触发异常检测+告警）。数据源为 EventLogger 的 SQLite 存储。 |
| `anomaly_detector.py` | ✅ 辅助 | Bash 命令异常检测器：基于规则检测高频失败、危险命令、异常时段等可疑模式。由 bash_router 按需调用。 |
| `alert_notifier.py` | ✅ 辅助 | Bash 审计告警通知器：将异常检测结果通过 SystemNotificationService 发送告警通知。 |

---

## API 端点

### GET /api/v1/audit/auth/logs

查询认证审计日志，支持过滤。

**Query 参数**：
- `start_time` / `end_time`: UTC timestamp 范围
- `event_type`: 事件类型（auth_success / auth_failure / rate_limit_exceeded）
- `client_ip`: IP 地址过滤
- `limit`: 返回记录数（默认 100，最大 1000）

**Response**：
```json
[
  {
    "timestamp": 1713000000.123,
    "event_type": "auth_failure",
    "client_ip": "192.168.1.100",
    "auth_source": null,
    "metadata": {"path": "/api/v1/chats"}
  }
]
```

### GET /api/v1/audit/auth/stats

获取认证审计统计信息。

**Response**：
```json
{
  "total_events": 1234,
  "auth_success_count": 1100,
  "auth_failure_count": 134,
  "rate_limit_count": 0,
  "unique_ips": 5,
  "top_failure_ips": [["192.168.1.100", 50]]
}
```

### GET /api/v1/audit/auth/export

导出认证审计日志。

**Query 参数**：
- `format`: 导出格式（csv / json）

**Response**：文件流（CSV 或 JSON）

---

## 依赖关系

### 内部依赖
- `app/middleware/auth_audit.py`：Auth 审计数据源（JSONL 文件路径 + AuthEventType 枚举）
- `myrm_agent_harness.agent.middlewares._session_context`：EventLogger（Bash 审计数据源）
- `app/services/system_notification_service`：告警通知持久化

### 被依赖方
- `app/api/router.py`：注册到主 API Router
