# chrome_e2e 域架构

## 架构概述

Chrome E2E Dev Gate 是测试入口的适配层。正式 pytest 只通过 monorepo 的 Browser Orchestrator daemon 访问专用 E2E Chrome；Cursor 日常浏览器使用独立 ChromeAgent；旧 mux 只保留给显式诊断路径。

```text
formal E2E  ──→  Dev Gate lease ──→ Browser Orchestrator ──→ Chrome :9333
Cursor 日常 ──→  ChromeAgent pipe-proxy ──→ ChromeAgent :9410
诊断旁路   ──→  mux/diagnostic_recovery.py（仅 MYRM_CHROME_MCP_DIAGNOSTIC=1）
```

详细 daemon 设计见 [browser-orchestrator/_ARCH.md](../../../../../scripts/dev/browser-orchestrator/_ARCH.md)。

## 文件清单

| 路径 | 职责 | I/O/P |
|------|------|-------|
| `gates/entry_guard.py` | formal 浏览器入口 fail-closed，禁止 ad-hoc mux 启动 | ✅ |
| `gates/lease_gate.py` | Browser Orchestrator lease attestation | ✅ |
| `gates/orphan_budget.py` | stray blank target 预算不变量 | ✅ |
| `gates/diagnostic_policy.py` | 诊断 mux 操作门禁 | ✅ |
| `mux/diagnostic_recovery.py` | 仅诊断模式的 recovery/reopen/rebuild | ✅ |
| `../browser_orchestrator/client.py` | daemon JSON-RPC client、预算快照和生命周期 | ✅ |
| `../browser_orchestrator/e2e.py` | formal `open_orchestrator_mcp_page` | ✅ |
| `../browser_orchestrator/core.py` | operation credits、host governor 观测和 daemon readiness | ✅ |
| `../e2e_core/effect_guard.py` | HTTP mutation effect guard | ✅ |
| `../chrome_mcp/client.py` | MCP 门面；formal 路径委托 orchestrator，诊断才使用 mux | ✅ |

## 正式路径不变量

- 每个测试必须先取得有效 wave lease；daemon 在 `session/create`、`page/create` 和 open transaction 前再次校验 lease。
- 每个 session 使用独立 BrowserContext 和 exact target ownership；cleanup 必须取得 `sealed`、`contextReleased`、`physicalReleased`。
- SHARED 只允许 READ 或 namespace 写；无法 namespace 化的全局写必须 PRIVATE+GLOBAL_WRITE。
- PRIVATE 必须提供合法 `private_reason`；`process_isolation` 没有实现，collect 阶段直接拒绝。
- formal E2E 禁止导入 `mux/diagnostic_recovery`，禁止 raw CDP 写入和窗口激活。

## 诊断边界

诊断 mux 不属于正式并发数据面，只能在 `MYRM_CHROME_MCP_DIAGNOSTIC=1` 下显式启用。诊断操作不能写入 formal session 的 ownership、lease 或 cleanup receipt，也不能成为默认恢复路径。
