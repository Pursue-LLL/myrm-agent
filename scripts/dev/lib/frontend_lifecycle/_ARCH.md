# frontend_lifecycle 模块架构

## 架构概述

共享 Next dev server（`:3000`，Turbopack，`turbopackFileSystemCacheForDev:false`）的**重启准入门**。冷编译 `/` 实测 85–282s（`dev_gate/contract.py`），而各调用方的等待预算（60/90/120/180s）更短；任何「探针超时 → SIGTERM → 冷编译重来」的路径都会形成正反馈风暴。本包把「能否 SIGTERM 前端」收敛为单一决策点：慢不等于死，只有**停滞证据**才放行启发式重启。

调用链：`dev-stack.sh` 的 kill 原语（`_kill_frontend_supervisor` / `_repair_orphan_frontend`）→ `python -m frontend_lifecycle admit`。所有决策与实际 kill 写入 `<state-dir>/frontend-restart-journal.jsonl`（含调用链 `ps` 祖先），用于归因。

## 决策规则（`policy.decide`，顺序即优先级）

| 条件 | 结果 |
|------|------|
| 确定性原因（`reset` / `pause` / `binding_mismatch` / `panic_residue`） | ALLOW，不观测、不依赖 python（bash 短路） |
| 无存活进程 | ALLOW `no_live_process` |
| 服务应答 `GET /` = 200（含 `client_hot_no`） | HEALTHY：拒绝重启（重启只会清掉水合记录并让所有 peer 重新冷编译） |
| 进程年龄 < `min_age` | DENY `young` |
| 连续不健康 ≥ `episode_cap`（3×282s） | ALLOW `episode_cap`（烧 CPU 却永不应答也算卡死） |
| 进程树 CPU 与日志在 `stall_sec` 窗口内均无增长 | ALLOW `stalled` |
| 其他 | DENY `progressing`（循环观测至 `wait_sec`） |

退出码：`0` 放行 · `10` 前端健康（勿重启，调用方当作成功） · `11` 拒绝（仍在编译 / 未证实卡死）。门自身出错按 `11` 处理（fail-closed：卡住的 heal 可恢复，误杀的编译不可恢复）。

## 文件清单

| 文件 | 职责 |
|------|------|
| `policy.py` | 纯函数 `decide()`、`Reason` / `Verdict` / `Observation` / `Policy`（阈值取自 `dev_gate.contract`，可由 `MYRM_FRONTEND_GATE_*` 缩放，仅供测试沙箱） |
| `process_tree.py` | `ps`/`lsof` 只读观测：进程树 CPU 时间、年龄、LISTEN 所有者 |
| `gate.py` | `admit()` 观测循环、`is_stalled()` 停滞判定、可注入 `Probes` |
| `episode.py` | `EpisodeStore`：跨调用持久化的「连续不健康时长」（flock + 原子替换，间隔超过 `gap_sec` 视为已恢复） |
| `journal.py` | 带调用链的 JSONL 决策/kill 日志（2MiB 轮转，写失败不影响决策） |
| `cli.py` / `__main__.py` | `admit` / `journal` 子命令，bash 的进程边界 |

## 依赖

- `dev_gate.contract`（阈值 SSOT）
- 被 [dev-stack.sh](../../dev-stack.sh) 调用；测试见 monorepo `scripts/dev/tests/frontend_lifecycle/`（风暴复现器 `test_restart_storm.py` 用真实 `dev-stack.sh` + 受控假 Next）
