# chrome_e2e 域架构

## 架构概述

Chrome E2E Dev Gate 维护者工具域：formal pytest（orchestrator）· Cursor mux MCP · diagnostic 三路径 SSOT。

```
formal E2E  ──→  browser-orchestrator daemon + lease gate
Cursor MCP  ──→  cdmcp-mux-autoconnect shim (:9333) + focus suppress
diagnostic  ──→  mux/diagnostic_recovery.py (MYRM_CHROME_MCP_DIAGNOSTIC=1 only)
```

详细 daemon 设计见 [browser-orchestrator/_ARCH.md](../../../../../scripts/dev/browser-orchestrator/_ARCH.md)。

## 文件清单

| 路径 | 职责 | I/O/P |
|------|------|-------|
| `gates/entry_guard.py` | §19.10 D3 mux entry fail-closed | ✅ |
| `gates/lease_gate.py` | §19.10 D1 orchestrator lease attestation | ✅ |
| `gates/orphan_budget.py` | TAB-5 stray blank budget invariant | ✅ |
| `gates/diagnostic_policy.py` | 统一 diagnostic-only mux 操作门禁 | ✅ |
| `mux/diagnostic_recovery.py` | diagnostic recovery/reopen/rebuild 实现 | ✅ |
| `../browser_orchestrator_client.py` | orchestrator daemon JSON-RPC 客户端（待迁入 orchestrator/） | ✅ |
| `../browser_orchestrator_e2e.py` | formal open_orchestrator_mcp_page | ✅ |
| `../browser_orchestrator.py` | operation credits + daemon readiness | ✅ |
| `../chrome_mcp_client.py` | mux MCP 客户端门面（orchestrator 条件分发） | ✅ |

## 遗留 flat re-export shim（lib/ 根）

**已删除（Batch-2）** — 全库 import 指向 `chrome_e2e.gates.*` / `chrome_e2e.mux.*`。

## 依赖

- [../_ARCH.md](../_ARCH.md)
- [dev_gate_contract.py](../dev_gate_contract.py)
- [scripts/dev/cdmcp-mux-autoconnect/](../../../../../scripts/dev/cdmcp-mux-autoconnect/)

## 约束

- formal chrome_e2e **禁止** import `mux/diagnostic_recovery`（static guard）
- Cursor MCP shim 见 `resilient-shim.mjs` — orchestrator env **不得** skip focus suppress
