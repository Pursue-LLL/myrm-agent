# shared/config/ 模块架构

## 架构概述

前后端共享的静态 JSON 配置。

## Normalize Contract

Legacy storage id remap 在前后端使用**同一算法**（与 [`providers.py`](../../myrm-agent-server/app/services/agent/params/providers.py) · [`providerIdentityMigration.ts`](../../myrm-agent-frontend/src/store/config/providerIdentityMigration.ts) 一致）：

1. `trim()` 首尾空白
2. `-` → `_`
3. `lower()` 小写
4. 查 `provider_legacy_remap.json`；未命中则返回 trim 后的原 id（不改大小写）

## 文件清单

| 文件 | 职责 | 消费者 |
|------|------|--------|
| `provider_legacy_remap.json` | 遗留 providerId → canonical storage id | `providers.py` · `providerIdentityMigration.ts` · Docker `/shared` · PyInstaller bundle · vitest · pytest |
| `kanban_move_guard.json` | 看板任务手动 move 的流转表：每个起点状态（含「原地不动」）服务端接受的目标状态 | [`kanban-transitions.ts`](../../myrm-agent-frontend/src/components/features/kanban/kanban-transitions.ts) 据此在发起前拦下必败的移动 · 服务端只在测试里读它，运行时不打包 |
| `kanban_blocked_reasons.json` | 服务端写入看板任务阻塞原因的英文句子，按 key 命名 | [`kanbanBlockedReason.ts`](../../myrm-agent-frontend/src/lib/kanban/kanbanBlockedReason.ts) 按整句匹配译成界面语言 · 服务端只在测试里读它，运行时不打包 |

## Kanban Blocked Reasons Contract

阻塞原因在服务端是一句英文（频道命令、诊断、活动流原样展示），看板卡片与抽屉按整句匹配成界面语言的文案，匹配不上就原样显示，
所以两边的句子必须逐字相同。`kanban_blocked_reasons.json` 是 `{key: 句子}`，key 同时是前端 `kanban.blockedReason.<key>` 的文案 key；
[`test_blocked_reason_contract.py`](../../myrm-agent-server/tests/services/kanban/test_blocked_reason_contract.py)
要求它与服务端常量完全一致。服务端新增、改动阻塞原因句子，或这张表有改动，都要让该测试保持通过，并在前端补上对应文案。

## Kanban Move Guard Contract

`kanban_move_guard.json` 是 `{起点状态: [可达目标状态]}`，覆盖全部 9 个状态。服务端规则仍在
[`move_orchestrator.move_task`](../../myrm-agent-server/app/services/kanban/move_orchestrator.py)；
[`test_move_guard_contract.py`](../../myrm-agent-server/tests/api/kanban/test_move_guard_contract.py)
把 9 × 9 对状态逐对打到真实的 `POST /kanban/tasks/{id}/move`，接受与否必须和这张表完全一致。
改服务端守卫或这张表，都要让该测试保持通过。
