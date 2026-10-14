# visual-diff 审批子模块

## 架构概述

提供多客户端双向结构化审批协议客户端实现、代码统一 Diff 高保真审查卡片、终端命令风险雷达（Blast Radius）与键盘单键快捷放行/拒绝交互（Roadmap ⑨ Item 59 P0）。
彻底解决 Codex App Server #21982 所揭示的长连接通信审批丢包、参数模糊与盲目放行痛点。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `visualDiffTypes.ts` | 核心契约 | 定义 StructuredApprovalRequest、Decision、FileDiffPayload 与 CommandRiskPayload | ✅ |
| `visualDiffService.ts` | 客户端服务 | 封装与后端 `/api/v1/approvals/bidirectional/*` 的请求、决策提交与离线降级 | ✅ |
| `VisualDiffApprovalCard.tsx` | 核心 UI | 代码 Diff 视图、命令风险雷达与键盘 1/2 单键快捷放行/拒绝卡片 | ✅ |
| `ApprovalNotificationBridge.ts` | 跨端适配 | Tauri 桌面端与 Web 端系统级交互式通知派发桥 | ✅ |
| `index.ts` | 门面导出 | 导出核心模型、服务与 UI 组件 | ✅ |

## 依赖关系

### 外部依赖
- `lucide-react` — 矢量图标（FileCode, Terminal, Check, X, ShieldAlert, AlertTriangle, Bookmark 等）

### 内部依赖
- `locales/{lang}.json` 的 `visualApproval` 命名空间 — 六语国际化词条
