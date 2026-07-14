# scripts/dev 模块架构

## 架构概述

本地开发启动脚本。由根 `scripts/myrm` / `myrm.ps1` 分发调用，不直接暴露给终端用户（用户使用 `myrm dev` / `myrm start`）。

**职责边界**：本目录只放 **栈启动/守门** 与 **MCP Chrome UI E2E 胶水**（`_ARCH.md` 文件表内条目）。可重复的 API/契约验证一律在 `myrm-agent-server/tests/`（`./myrm test` / `./myrm test -m e2e`），禁止在此新增「半 pytest」一次性联调脚本。

## 文件清单

| 文件 | 平台 | 职责 |
|------|------|------|
| `setup.sh` / `setup.ps1` | 双平台 | clone 后首次依赖安装：monorepo 自动 editable harness；OSS-only 走 PyPI `uv sync`；`patchright install chromium` + `bun install` + `ensure-next-native-swc.sh` |
| `dev.sh` / `dev.ps1` | 双平台 | 仅后端 :8080 |
| `start.sh` | Unix | 委托 `dev-stack ensure`（:8080 + :3000 idempotent；frontend 冷编译最长 120s）；`chrome-devtools-mcp` 进程 >1 时 stderr WARN |
| `start.ps1` | Windows | 后端 :8080 + 前端 `bun run dev` :3000（无 LISTEN 编译等待 / MCP WARN；见 `start.sh` Unix 行为） |
| `run_server.sh` / `run_server.ps1` | 双平台 | 低层后端启动（`myrm start` 内部使用） |
| `instinct-inbox-seed.py` | 双平台 | Instinct Inbox mock 数据 seed（HTTP 或 `--direct`） |
| `test-instinct-inbox-e2e.sh` | Unix | Instinct Inbox API E2E + GLOBAL_WRITE mock-draft seed；UI 用 MCP chrome-devtools |
| `dev-stack.sh` | Unix | 本地 dev 栈 SSOT：`ensure` / `attach` / `reset` / `status`；`cmd_ensure` 三分支：已热栈 idempotent OK；冷栈 + wave pin + 端口在听 → attach-wait；冷栈 + wave pin + 栈 down → `STACK_FAIL`；**必须**委托 **stack_supervisor** 单写者；state `~/.local/state/myrm-dev/` |
| `stack-supervisor.sh` | Unix | Dev 栈守护进程启动器 + RPC 客户端入口；见 [stack_supervisor/_ARCH.md](stack_supervisor/_ARCH.md) |
| `ensure-next-native-swc.sh` | Unix | 缺平台 `@next/swc-*` 时 `bun install --no-save`（防 WASM 慢编译）；setup 与 dev-stack 双路径 |
| `ensure-myrm-chrome-e2e.sh` | Unix | 拉起/验证 Myrm 专用 E2E Chrome（`:9333`，零 Allow）；栈热时首开 `:3000` 而非 blank |
| `prune-myrm-chrome-e2e-blank-tabs.sh` | Unix | 仅按 transient ledger 回收死亡 owner 的精确 targetId；从不按 URL/blank/重复页推断 |
| `myrm-chrome-e2e-lib.sh` | Unix | E2E Chrome 路径/port 常量与 CDP 健康探测 |
| `runtime-drift.sh` | Unix | 机械校验 `runtimeId` 未漂移（`--expect`；exit 2 = `RUNTIME_DRIFT`） |
| `wave-e2e-lease.sh` | Unix | `./myrm test -m e2e` LIVE_AGENT 租约；最后一个 lease 释放时原子关闭 Wave |
| `wave_orchestrator/` | Unix | Immutable test wave + READ lease + reset 门禁；见 [wave_orchestrator/_ARCH.md](wave_orchestrator/_ARCH.md) |
| `chrome-e2e-preflight.sh` | Unix | 首 Agent完整 reconcile/client_hot；attach 用一次聚合只读快照 fail-fast；输出 `CHROME_E2E_HEALTH_JSON` |
| `chrome-e2e-model-seed.mjs` | Bun | 新对话 UI E2E 前置：无 defaultModel 时从 `.env.test` 写入 providers |
| `chrome-e2e-seed-providers.mjs` | Bun | seed 逻辑模块（local 模式免 WebUI 登录） |
| `wave-resource-lease.sh` | Unix | `./myrm` E2E 脚本 RESOURCE_WRITE/GLOBAL_WRITE 租约 + release 自动 ledger 清理 |
| `test-subagent-dashboard-e2e.sh` | Unix | Subagent Dashboard E2E — GLOBAL_WRITE lease + config snapshot restore + ledger register chat；API prepare + UI MCP |
| `subagent-dashboard-e2e-auth.mjs` | 双平台 | P2c E2E 共享 WebUI login + authenticated fetch |
| `subagent-dashboard-e2e-prepare.mjs` | 双平台 | P2c prepare：seed、创建 chat、`registerWaveLedger`、SSE delegate → JSON |
| `subagent-dashboard-e2e-verify.mjs` | 双平台 | P2c verify：authenticated REST cancel 探测 subagent 已停止 |
| `kanban-chrome-e2e-prepare.mjs` | 双平台 | Kanban LLM API prepare（provider seed + stream add_task + GET task 断言） |
| `test-kanban-chrome-e2e.sh` | Unix | Kanban Chrome E2E — GLOBAL_WRITE lease + config snapshot restore + board/chat/task ledger + UI hold window |
| `lib/backend_bg.sh` | Unix | 后台启动 server（`dev.sh` / `start.sh` source）；monorepo 下检测 harness 非 editable 时 **exit 1**（`MYRM_SKIP_HARNESS_EDITABLE_CHECK=1` 跳过） |
| `lib/dev_state_paths.sh` | Unix | pid/log 路径 SSOT + 子目录回退读取；见 [lib/_ARCH.md](lib/_ARCH.md) |
| `lib/` | Unix | 开发子脚本库目录，见 [lib/_ARCH.md](lib/_ARCH.md) |

## WebUI E2E（MCP chrome-devtools + Myrm E2E Chrome :9333）

产品 WebUI 端到端 UI 验收使用 **MCP chrome-devtools** + **Myrm 专用 E2E Profile**（`./myrm ready --chrome` 自动拉起，**零 Allow**），禁止 `@playwright/test`、pytest 无头浏览器，禁止 autoConnect 主 Chrome / `MyrmChromeMcp`。

| 脚本 | 职责 |
|------|------|
| `ensure-myrm-chrome-e2e.sh` | 专用 Chrome `--remote-debugging-port=9333`；首次人工登录一次后持久化 |
| `subagent-dashboard-e2e-prepare.mjs` | 登录 API、seed provider/YOLO、创建 chat、agent-stream delegate → JSON |
| `subagent-dashboard-e2e-verify.mjs` | UI cancel 后 REST 验证 subagent 已停止 |
| `test-subagent-dashboard-e2e.sh` | 确保 backend :8080 + 运行 prepare |
| `test-instinct-inbox-e2e.sh` | Instinct Inbox API pytest + seed-mock；UI 走 chrome-devtools |
| `kanban-chrome-e2e-prepare.mjs` | Kanban API prepare（LLM add_task + REST 断言）；UI 走 chrome-devtools |
| `test-kanban-chrome-e2e.sh` | Kanban UI 场景正式入口；负责 GLOBAL_WRITE、资源登记和结束清理 |
| `chrome-e2e-preflight.sh` | 服务健康 + E2E Chrome + mux daemon + CDP WS → `CHROME_E2E_READY` |

**Chrome E2E 稳定性清单**

1. **`./myrm ready --chrome`** 为 SSOT；禁止手连主 Chrome autoConnect（会弹 Allow）
2. **mux 模式**：多 Agent / 多 Cursor 客户端可并行 UI E2E（`cdmcp-mux-autoconnect`）；vanilla 多进程仍会死锁 → `scripts/dev/enable-chrome-devtools-mcp.sh`
3. **禁止 `list_pages` / `select_page` 探活**（无 timeout，曾挂起 30min+）；探活只读 `CHROME_E2E_HEALTH_JSON.clientHot`
4. MCP：**单步** `new_page(url=$E2E_UI_BASE/…, timeout=15000)` 开自有 tab → 同次取 **pageId + exact targetId**；`navigate_page` 默认 **15s**；测完 **`close_page`**
5. **tab 卫生**：只关闭自有 pageId；崩溃 GC 只关闭 transient ledger 中死亡 owner 的 exact targetId，禁止 URL 去重
6. **集成测试进程纪律**：并行 Agent **`./myrm ready --attach --chrome`**；栈 **`dev-stack ensure`**；**禁止** Agent shell `bun run dev &`
7. **runtimeId + Wave + Stack Pin**：`CHROME_E2E_HEALTH_JSON.runtimeId` — `wave open` 冻结并钉死栈 → `lease acquire READ` → 断言前 `./myrm runtime-drift --expect <id>`；open wave 或持 lease 时 `ensure/reset/restart` 机械拒绝；并行 Agent 仅 `--attach --chrome`
8. **client_hot + transient target**：`ready --chrome` 用短生命周期 exact target 预热 client chunk，hydrate 后立即关闭并注销；mux 按 client 隔离 page ownership，Agent 必须 `new_page` 自己的 tab；`shell_hot`（curl `/`）≠ UI hydrate 完成；改码后 UI 测 **`./myrm restart --chrome`** 开新 wave
9. **CDP 单写者**：项目内 pytest/bun raw `/json/new` 永久拒绝（`CDP_WRITE_DENIED`）；仅 supervisor client warmup 使用 `MYRM_CDP_WARMUP=1`，正式 UI E2E 只能经 mux MCP；外部 Playwright/raw CDP 属明确禁止项

**勿引用（已移除）**：`browser-delegate-chrome-e2e.mjs`、`clarify-chrome-e2e.mjs`、`start-chrome-mcp-debug.sh`（第二 Chrome / Allow 冲突）；`browser-delegate-e2e-once.mjs`、`render-ui-gap-e2e-prepare.mjs`、`notify-channel-e2e-prepare.mjs`、`cron-gap-e2e-prepare.mjs`、`test-cron-gap-e2e.sh`（API 重复 → `myrm-agent-server/tests/api/agent/`）；`ui_pong_chrome_verify.py`、`render_ui_chrome_verify.py`、`wfel-settings-ui-check.py`（主 Chrome CDP → 用 `:9333` + `tests/` 或 MCP）；`subagent-dashboard-e2e-poll.mjs`（debug 轮询，正式链用 prepare + verify）；`test-instinct-inbox-seed.py`（已改名 `instinct-inbox-seed.py`）。品牌图标生成见 `myrm-agent-desktop/scripts/inset-app-icon.py`。

**MCP 配置（Cursor）**：本仓无 mux 安装脚本；维护者 monorepo 见上层 `scripts/dev/CHROME_MCP_E2E.md` 与 `mcp-chrome-devtools.server.json`。OSS 贡献者仅需 `chrome-e2e-preflight.sh` + `ensure-myrm-chrome-e2e.sh`。

环境变量：`E2E_UI_BASE`（默认 `http://127.0.0.1:3000`）、`E2E_API_BASE`（默认 `http://127.0.0.1:8080`）、`E2E_ADMIN_PASSWORD`。

## 依赖

- [scripts/lib/resolve_agent_root.sh](../lib/resolve_agent_root.sh) — 解析安装根目录
- [scripts/lib/start_server.sh](../lib/start_server.sh) — 后端进程启动
