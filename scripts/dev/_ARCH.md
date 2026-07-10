# scripts/dev 模块架构

## 架构概述

本地开发启动脚本。由根 `scripts/myrm` / `myrm.ps1` 分发调用，不直接暴露给终端用户（用户使用 `myrm dev` / `myrm start`）。

## 文件清单

| 文件 | 平台 | 职责 |
|------|------|------|
| `setup.sh` / `setup.ps1` | 双平台 | clone 后首次依赖安装：monorepo 自动 editable harness；OSS-only 走 PyPI `uv sync`；`patchright install chromium` + `bun install` |
| `dev.sh` / `dev.ps1` | 双平台 | 仅后端 :8080 |
| `start.sh` | Unix | 后端 :8080 + 前端 `bun run dev` :3000；HTTP `127.0.0.1:3000` 健康检查；`:3000` LISTEN 但 HTTP 未就绪时 poll **墙钟 30s**（2s curl + 1s sleep）；`chrome-devtools-mcp` 进程 >1 时 stderr WARN |
| `start.ps1` | Windows | 后端 :8080 + 前端 `bun run dev` :3000（无 LISTEN 编译等待 / MCP WARN；见 `start.sh` Unix 行为） |
| `run_server.sh` / `run_server.ps1` | 双平台 | 低层后端启动（`myrm start` 内部使用） |
| `test-instinct-inbox-seed.py` | 双平台 | Instinct Inbox mock 数据 seed（HTTP 或 `--direct`） |
| `test-instinct-inbox-e2e.sh` | Unix | Instinct Inbox API E2E（`open-perplexity/scripts/dev/test.sh`）；UI 用 MCP chrome-devtools |
| `chrome-e2e-preflight.sh` | Unix | MCP E2E 前置：Chrome/CDP/服务健康检查 |
| `test-subagent-dashboard-e2e.sh` | Unix | Subagent Dashboard E2E — API prepare（delegate via agent-stream）；**本地 monorepo** 须 editable harness（`./myrm ready` 自愈），禁止 cp site-packages；**非 CI 发布链路** |
| `subagent-dashboard-e2e-auth.mjs` | 双平台 | P2c E2E 共享 WebUI login + authenticated fetch |
| `subagent-dashboard-e2e-prepare.mjs` | 双平台 | P2c prepare：seed provider/YOLO、创建 chat、SSE delegate、GET `/subagents` 断言、`E2E_HOLD_MS` 保活 → JSON |
| `subagent-dashboard-e2e-verify.mjs` | 双平台 | P2c verify：authenticated REST cancel 探测 subagent 已停止 |
| `subagent-dashboard-e2e-poll.mjs` | 双平台 | 诊断：prepare 后 list 持久性轮询 + cancel |
| `kanban-chrome-e2e-prepare.mjs` | 双平台 | Kanban LLM API prepare（provider seed + stream add_task + GET task 断言） |
| `lib/backend_bg.sh` | Unix | 后台启动 server（`dev.sh` / `start.sh` source）；monorepo 下检测 harness 非 editable 时 **exit 1**（`MYRM_SKIP_HARNESS_EDITABLE_CHECK=1` 跳过） |
| `lib/` | Unix | 开发子脚本库目录，见 [lib/_ARCH.md](lib/_ARCH.md) |

## WebUI E2E（MCP chrome-devtools，禁止 @playwright/test）

产品 WebUI 端到端 UI 验收使用 **MCP chrome-devtools `--autoConnect`**（用户主 Chrome 登录态 `:3000`），禁止 `@playwright/test`、pytest 无头浏览器，**禁止**启动第二个隔离 Chrome（`MyrmChromeMcp` / 自定义 `--user-data-dir` / 固定 `:9222` 空 profile）。

| 脚本 | 职责 |
|------|------|
| `subagent-dashboard-e2e-prepare.mjs` | 登录 API、seed provider/YOLO、创建 chat、agent-stream delegate → JSON |
| `subagent-dashboard-e2e-verify.mjs` | UI cancel 后 REST 验证 subagent 已停止 |
| `test-subagent-dashboard-e2e.sh` | 确保 backend :8080 + 运行 prepare |
| `test-instinct-inbox-e2e.sh` | Instinct Inbox API pytest + seed-mock；UI 走 chrome-devtools |
| `kanban-chrome-e2e-prepare.mjs` | Kanban API prepare（LLM add_task + REST 断言）；UI 走 chrome-devtools |
| `chrome-e2e-preflight.sh` | MCP chrome-devtools 前置检查（服务健康、DevToolsActivePort、CDP WS、MCP 条数≤1、无 MyrmChromeMcp）→ `CHROME_E2E_READY` |

**Chrome E2E 稳定性清单（MCP `--autoConnect`）**

1. 仅使用**主 Chrome 登录态**；禁止 `MyrmChromeMcp` / 第二 `--user-data-dir` / 曾用的 `start-chrome-mcp-debug.sh`（**已删除**）
2. `chrome://inspect/#remote-debugging` → Allow；`DevToolsActivePort` mtime 须为本次会话（跑 `chrome-e2e-preflight.sh` 或 monorepo 根 `scripts/dev/chrome-mcp-preflight.sh`）
3. **浏览器任务只开 1 个 Agent 对话**；多条对话 = 多条 `chrome-devtools-mcp` 进程，易死锁。卡死时 Cmd+Q Cursor
4. **禁止 `list_pages` 探活**（无 timeout，曾挂起 30min+）；用 `new_page`（`timeout`≤5000，`isolatedContext` 为字符串名）起手
5. MCP 握手期间**勿点击 Chrome 窗口**（Chrome 150 远程调试下有 SIGSEGV 报告）；盯 Allow 弹窗即可
6. MCP 技巧：先 `new_page` → `about:blank`（timeout≤5000），再 `navigate_page` → `http://127.0.0.1:3000/...`（避免 Next.js 冷启动 navigation timeout）；`navigate` 超时时用 `take_snapshot` 验证，勿盲重试
7. **集成测试进程纪律**：整场 E2E **`./myrm ready` 一次**；仅 server/harness Python 变更后 **`./myrm restart`**；**禁止**多 Agent 并行 `start`/`bun run dev`（`dev.ts` 健康时跳过 port kill，但并行 start 仍会互抢 dev lock）

**已删除（勿引用）**：`browser-delegate-chrome-e2e.mjs`、`clarify-chrome-e2e.mjs`、`start-chrome-mcp-debug.sh` — 曾拉起第二 Chrome，与 `--autoConnect` 冲突。

**MCP 配置片段（Cursor）**：`open-perplexity/scripts/dev/mcp-chrome-devtools.server.json`；`enable-chrome-devtools-mcp.sh` / `disable-chrome-devtools-mcp.sh` 按需开关（日常可常开，见 `ifm/profile.yaml` 浏览器 §12）。

环境变量：`E2E_UI_BASE`（默认 `http://127.0.0.1:3000`）、`E2E_API_BASE`（默认 `http://127.0.0.1:8080`）、`E2E_ADMIN_PASSWORD`。

## 依赖

- [scripts/lib/resolve_agent_root.sh](../lib/resolve_agent_root.sh) — 解析安装根目录
- [scripts/lib/start_server.sh](../lib/start_server.sh) — 后端进程启动
