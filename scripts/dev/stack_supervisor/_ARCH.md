# stack_supervisor 模块架构

## 架构概述

本地 dev 栈 **单写者守护进程**。解决「多 Agent / 多次 ensure 互杀」与「warmth/epoch 假阳性」问题。

- **唯一 kill/start 入口**：`ensure` / `reset` 经 supervisor 串行化（`threading.Lock`）
- **attach 只读**：并行 Agent 等待栈热，无副作用
- **看门狗**：每 30s live probe + GC 失效 warmth/epoch/stale pid；若栈曾热后失温且 HTTP 不通，**5min 冷却内单次 auto-ensure 自愈**
- **真值**：`supervisor-state.json` 来自 pid+port+HTTP，不单独信缓存

## 文件清单

| 文件 | 职责 |
|------|------|
| `stack-supervisor.sh` | Bash 启动器：`start` / `stop` / `rpc <cmd>` |
| `__main__.py` | `python -m stack_supervisor` CLI 入口 |
| `daemon.py` | Unix socket RPC 服务 + 看门狗线程 + 失温冷却自愈 |
| `client.py` | RPC 客户端；`dev-stack.sh` 委托入口 |
| `probe.py` | live 探活（pid / lsof / HTTP） |
| `state_gc.py` | 进程死亡时清理 warmth、epoch、stale pid |
| `paths.py` | 路径解析（`AGENT_ROOT` / state dir） |
| `rpc_types.py` | `RpcResponse` / `RpcCommand` |

## RPC 命令

| cmd | 行为 |
|-----|------|
| `ensure` | 串行调用 `dev-stack.sh ensure`（`MYRM_SUPERVISOR_BYPASS=1`） |
| `attach` | 委托 `dev-stack.sh attach`（无互斥） |
| `reset` | 串行 `dev-stack.sh reset`；成功时清除「曾热」记忆，禁止 intentional-stop 后 auto-heal |
| `status` | GC + `dev-stack.sh status` |
| `ping` | 存活探测 |
| `shutdown` | 停止 daemon |

环境变量：`MYRM_SUPERVISOR_WATCHDOG_SEC`（默认 30）、`MYRM_SUPERVISOR_HEAL_COOLDOWN_SEC`（默认 300，失温后单次 auto-ensure 冷却）。

## 集成

- `dev-stack.sh` **必须**委托 supervisor（无直跑 fallback）；RPC 失败 **exit 1**（`STACK_FAIL`）
- `dev-stack.sh` `reset` 在活跃 wave READ lease 时 **exit 1**（`WAVE_STACK_WRITE_DENIED`）；见 [../wave_orchestrator/_ARCH.md](../wave_orchestrator/_ARCH.md)
- supervisor 子调用设 `MYRM_SUPERVISOR_BYPASS=1` 防递归
- `./myrm stop` → `reset` 后 `stack-supervisor.sh stop`
- `frontend-warmup.sh`：warmth 命中前要求 `_lock_supervisor_alive`（frontend lock pid 存活；定义于 warmup.sh，preflight 直 source）
- `chrome-e2e-preflight.sh`：`MYRM_CHROME_E2E_ATTACH=1` 时 curl 失败 **直接 fail**，不 ensure

## 状态目录

`~/.local/state/myrm-dev/`：

- `supervisor.pid` / `supervisor.sock`
- `supervisor-state.json` — live 探活快照
- `supervisor.log` — daemon 日志

## 依赖

- [dev-stack.sh](../dev-stack.sh) — 实际栈启停逻辑（supervisor 不重复实现）
- [../_ARCH.md](../_ARCH.md)
