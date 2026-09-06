# dev/lib Domain Repack Plan

> Status: **P1–P6 DONE · shims removed · imports consolidated to sub-package paths** (2026-08-13)
> **Test SSOT**: monorepo `open-perplexity/scripts/dev/tests/` only（`myrm-agent/scripts/dev/tests/` 已合并删除 · `conftest.py` 注入 `DEV_LIB`）.
> Goal: zero behavior change; improve navigability; prevent import/drift regressions.

当前浏览器数据面边界：`browser_orchestrator/` 是 formal Chrome E2E 的唯一 CDP 调度入口；`mux/` 与 `chrome_mcp/` 仅作为适配、诊断和兼容域，不能重新成为并发数据面。并发预算、lease、ownership 和 observed cleanup 的 SSOT 见 `browser_orchestrator/` 与 `chrome_e2e/_ARCH.md`。

## Principles

1. **Shim-first**: every moved module keeps a thin re-export file at its old flat path until Phase 4.
2. **One domain per PR**: merge-friendly; run targeted tests after each domain.
3. **No logic edits** in move commits (git mv + shims + import path updates inside moved package only).
4. **sys.path unchanged**: callers keep `sys.path.insert(0, ".../dev/lib")` + `from dev_gate_contract import ...`.
5. **Monorepo tests SSOT**: `open-perplexity/scripts/dev/tests/`（~177 files；`conftest.py` 注入 `DEV_LIB` + `scripts/dev` 供 `isolated_runtime` 等 monorepo 模块）.

## Target Tree

```text
dev/lib/
├── _ARCH.md                    # update file table each phase
├── DOMAIN_REPACK_PLAN.md         # this file
├── dev_gate/                   # coordinator, store, session, private credit
├── cdp_chat/                   # chat UI automation + turn contracts
├── mux/                        # 诊断/兼容 transport, supervisor, probes
├── chrome_mcp/                 # formal MCP 适配层 + protocol
├── browser_orchestrator/       # orchestrator daemon client + page lifecycle
├── e2e_core/                   # e2e_* + stack/runtime/auth/hygiene SSOT
├── chrome_e2e/                 # (existing) gates + mux diagnostic
├── e2e_session_runtime/        # (existing) snapshot, heartbeat, lifecycle
├── e2e_live_flows/             # (existing) live flow runners
└── (lib root)                  # no flat .py shims remain after P6
```

## Shim Template

```python
"""Compatibility shim — moved to `<package>.<module>`. Do not add logic here."""
from <package>.<module> import *  # noqa: F403
```

## File Mapping (124 modules)

### dev_gate/ (15)

| Old path | New path |
|----------|----------|
| `dev_gate_async_queue.py` | `dev_gate/async_queue.py` |
| `dev_gate_cli.py` | `dev_gate/cli.py` |
| `dev_gate_contract.py` | `dev_gate/contract.py` |
| `dev_gate_coordinator.py` | `dev_gate/coordinator.py` |
| `dev_gate_event_hub.py` | `dev_gate/event_hub.py` |
| `dev_gate_event_wait.py` | `dev_gate/event_wait.py` |
| `dev_gate_session.py` | `dev_gate/session.py` |
| `dev_gate_signoff_export.py` | `dev_gate/signoff_export.py` |
| `dev_gate_status.py` | `dev_gate/status.py` |
| `dev_gate_store.py` | `dev_gate/store.py` |
| `private_resource_controller.py` | `dev_gate/private_resource_controller.py` |
| `solo_launch_gate.py` | `dev_gate/solo_launch_gate.py` |
| `cleanup_observed_seal.py` | `dev_gate/cleanup_observed_seal.py` |
| `desktop_seat_controller.py` | `dev_gate/desktop_seat_controller.py` |
| `owner_identity.py` | `dev_gate/owner_identity.py` |

### cdp_chat/ (12)

| Old path | New path |
|----------|----------|
| `cdp_chat_bootstrap.py` | `cdp_chat/bootstrap.py` |
| `cdp_chat_input.py` | `cdp_chat/input.py` |
| `cdp_chat_resume.py` | `cdp_chat/resume.py` |
| `cdp_chat_submit.py` | `cdp_chat/submit.py` |
| `cdp_chat_support.py` | `cdp_chat/support.py` |
| `cdp_chat_transport.py` | `cdp_chat/transport.py` |
| `cdp_chat_turn.py` | `cdp_chat/turn.py` |
| `cdp_chat_ui.py` | `cdp_chat/ui.py` |
| `live_turn_wait.py` | `cdp_chat/live_turn_wait.py` |
| `mcp_chat_ui.py` | `cdp_chat/mcp_ui.py` |
| `resume_turn_contract.py` | `cdp_chat/resume_turn_contract.py` |
| `send_turn_contract.py` | `cdp_chat/send_turn_contract.py` |

### mux/ (7)

| Old path | New path |
|----------|----------|
| `mux_attach_force_restart.py` | `mux/attach_force_restart.py` |
| `mux_load.py` | `mux/load.py` |
| `mux_responsive_probe.py` | `mux/responsive_probe.py` |
| `mux_upstream_admission.py` | `mux/upstream_admission.py` |
| `transport_supervisor.py` | `mux/transport_supervisor.py` |
| `transport_recovery_core.py` | `mux/transport_recovery_core.py` |
| `mcp_transport_adapter.py` | `mux/transport_adapter.py` |

### chrome_mcp/ (7)

| Old path | New path |
|----------|----------|
| `chrome_mcp_client.py` | `chrome_mcp/client.py` |
| `chrome_mcp_errors.py` | `chrome_mcp/errors.py` |
| `mcp_protocol.py` | `chrome_mcp/protocol.py` |
| `mcp_page_helpers.py` | `chrome_mcp/page_helpers.py` |
| `mcp_page_lease_heartbeat.py` | `chrome_mcp/page_lease_heartbeat.py` |
| `mcp_snapshot.py` | `chrome_mcp/snapshot.py` |
| `mcp_ui_driver.py` | `chrome_mcp/ui_driver.py` |

### browser_orchestrator/ (6)

| Old path | New path |
|----------|----------|
| `browser_orchestrator.py` | `browser_orchestrator/core.py` |
| `browser_orchestrator_client.py` | `browser_orchestrator/client.py` |
| `browser_orchestrator_e2e.py` | `browser_orchestrator/e2e.py` |
| `e2e_page_open_orchestrator.py` | `browser_orchestrator/page_open.py` |
| `page_create_transaction.py` | `browser_orchestrator/page_create_transaction.py` |
| `frontend-client-warmup.py` | `browser_orchestrator/frontend_client_warmup.py` |

Note: `warm_shell_registry.py` stays in **e2e_core/** (TAB-6 SSOT, not orchestrator daemon).

### e2e_core/ (55)

All remaining flat `e2e_*.py`, plus:

| Old path | New path |
|----------|----------|
| `e2e_orchestrator.py` | `e2e_core/orchestrator.py` |
| `warm_shell_registry.py` | `e2e_core/warm_shell_registry.py` |
| `guardrail_e2e_ssot.py` | `e2e_core/guardrail_ssot.py` |
| `stack_mutation_policy.py` | `e2e_core/stack_mutation_policy.py` |
| `stack_heal_coordinator.py` | `e2e_core/stack_heal_coordinator.py` |
| `signoff_stack_preflight.py` | `e2e_core/signoff_stack_preflight.py` |
| `signoff_stack_heal.py` | `e2e_core/signoff_stack_heal.py` |
| `gate_epoch_preflight.py` | `e2e_core/gate_epoch_preflight.py` |
| `epoch_delivery_plane.py` | `e2e_core/epoch_delivery_plane.py` |
| `runtime_identity.py` | `e2e_core/runtime_identity.py` |
| `runtime_probe.py` | `e2e_core/runtime_probe.py` |
| `wave_state_paths.py` | `e2e_core/wave_state_paths.py` |
| `verify_backend_seed.py` | `e2e_core/verify_backend_seed.py` |
| `host_resource_governor.py` | `e2e_core/host_resource_governor.py` |
| `host_governor_benchmark.py` | `e2e_core/host_governor_benchmark.py` |
| `peer_count_ssot.py` | `e2e_core/peer_count_ssot.py` |
| `process_identity.py` | `e2e_core/process_identity.py` |
| `real_user_home.py` | `e2e_core/real_user_home.py` |
| `infra_browser_registry.py` | `e2e_core/infra_browser_registry.py` |
| `browser_tab_hygiene.py` | `e2e_core/browser_tab_hygiene.py` |
| `idle_tab_hygiene.py` | `e2e_core/idle_tab_hygiene.py` |
| `idle_hygiene_scheduler.py` | `e2e_core/idle_hygiene_scheduler.py` |
| `cdp_write_guard.py` | `e2e_core/cdp_write_guard.py` |
| `cursor_mcp_isolation.py` | `e2e_core/cursor_mcp_isolation.py` |
| `env_test_shell_lint.py` | `e2e_core/env_test_shell_lint.py` |
| `llm_receipt.py` | `e2e_core/llm_receipt.py` |
| `pytest_zero_selected.py` | `e2e_core/pytest_zero_selected.py` |

Remaining flat `e2e_*.py` → `e2e_core/<suffix>.py` (strip `e2e_` prefix).

### Unchanged packages

- `chrome_e2e/` (8 modules)
- `e2e_session_runtime/` (5 modules)
- `e2e_live_flows/` (7 modules)

## Phased Rollout

| Phase | Domain | Files | Gate tests |
|-------|--------|-------|------------|
| **P1** | `dev_gate/` | 15 | **DONE** — 172 passed; module-alias shims |
| **P2** | `cdp_chat/` | 12 | `test_cdp_chat_*.py`, `test_send_turn_contract.py` |
| **P3** | `mux/` + `chrome_mcp/` | 14 | `test_mux_*.py`, chrome_mcp static |
| **P4** | `browser_orchestrator/` | 6 | orchestrator + warm shell integration tests |
| **P5** | `e2e_core/` | 55 | `test_e2e_*.py` subset (~40 files) |
| **P6** | Remove shims | 0 | **DONE** — full `scripts/dev/tests/` + one chrome_e2e smoke |

Each phase checklist:

1. `git mv` files into package
2. Add `__init__.py` (empty or explicit exports)
3. Fix **intra-package** relative imports only
4. Add root-level shim for every moved module
5. Update `dev/lib/_ARCH.md` file table
6. Run phase gate tests via `scripts/dev/run-pytest-safe.sh`
7. No chrome_e2e live run required until P6 (optional P1 smoke if dev_gate touched)

## Intra-Package Import Rule

Inside `dev_gate/coordinator.py`:

```python
from dev_gate.store import DevGateStore      # OK after P1
from dev_gate_contract import CONTRACT_VERSION  # OK via shim during P1–P5
```

Prefer package imports within same domain; cross-domain keeps flat shim imports until P6.

## Cross-Cutting Callers (do not break)

| Caller | Pattern |
|--------|---------|
| `scripts/dev/test.sh` | `sys.path.insert` + flat imports |
| `scripts/dev/lib/e2e_bootstrap.sh` | python `-c` inline imports |
| `scripts/dev/tests/*.py` | `conftest.py` 注入 `DEV_LIB`；新测例优先 `from e2e_core.*` / `from dev_gate.*`（P6 前 shim 仍可用） |
| `myrm-agent-server/tests/conftest.py` | may import dev_gate modules |

All continue working via shims through P5.

## Rollback

Each phase is one revert commit (mv + shims). Do not partial-revert shims without reverting moves.

## Post-P6 Cleanup

1. ✅ Delete root shims — 105 flat shims removed
2. ✅ Bulk-update `from dev_gate_contract` → `from dev_gate.contract` (codemod 1170 imports + 8 `.sh` paths)
3. ✅ Consolidate monorepo `scripts/dev/lib/` — 该目录为 monorepo 专用资产（phase-c ramp / dgep / resource-soak 等），与 OSS 子包路径无重复；SSOT 收敛至 `myrm-agent/scripts/dev/lib/e2e_core/guardrail_ssot.py`
4. ✅ Add CI check: fail if new `.py` lands flat in `dev/lib/` root — `test_repack_deleted_module_paths_static.py` 同时覆盖测试侧引用与 lib 根 flat 落地（白名单：myrm-agent 根 `dev_paths.py`；根仓根 10 个资产）

## Risk Controls

| Risk | Mitigation |
|------|------------|
| Circular import | move one domain at a time; shims break cycles at old boundaries |
| Shell hardcoded paths | `.sh` files reference flat filenames — shims preserve paths |
| Duplicate module name in package | strip redundant prefix (`dev_gate_contract` → `dev_gate/contract.py`) |
| Merge conflicts | P1 smallest first; announce freeze window for e2e_core (P5) |
