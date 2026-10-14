# services/approvals/bidirectional — 双向结构化审批协议与 Diff 提取模块

## 架构概述

提供多客户端双向结构化审批协议（Bidirectional Approval Transport Protocol）、文件代码统一 Diff 生成、终端命令危险等级雷达（Blast Radius）与客户端决策 ACK 回执支持（Roadmap ⑨ Item 59 P0）。
彻底解决 Codex App Server #21982 所揭示的长连接通信审批丢包、参数模糊与盲目放行风险。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `protocol_types.py` | 核心契约 | 定义 StructuredApprovalRequest、Decision、FileDiffPayload 与 CommandRiskPayload | ✅ |
| `bidirectional_approval_service.py` | 核心服务 | Diff 计算、终端高危模式识别、单调递增序列号管理与决策 ACK 回执 | ✅ |
| `__init__.py` | 门面导出 | 导出核心模型与服务单例 | ✅ |

## 依赖关系

### 内部依赖
- `difflib`, `re`, `time`, `uuid` — 标准差分计算与危险指令正则雷达

### 被依赖方
- `app.api.approvals.bidirectional_router` — 暴露 REST API 端点供前端与桌面端卡片消费
