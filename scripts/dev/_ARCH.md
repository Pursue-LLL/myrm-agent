# scripts/dev 模块架构

## 架构概述

本地开发启动脚本。由根 `scripts/myrm` / `myrm.ps1` 分发调用，不直接暴露给终端用户（用户使用 `myrm dev` / `myrm start`）。

## 文件清单

| 文件 | 平台 | 职责 |
|------|------|------|
| `setup.sh` / `setup.ps1` | 双平台 | clone 后首次 `uv sync` + `patchright install chromium` + `bun install` |
| `dev.sh` / `dev.ps1` | 双平台 | 仅后端 :8080 |
| `start.sh` / `start.ps1` | 双平台 | 后端 :8080 + 前端 `bun run dev` :3000 |
| `run_server.sh` / `run_server.ps1` | 双平台 | 低层后端启动（`myrm start` 内部使用） |
| `test-instinct-inbox-seed.py` | 双平台 | Instinct Inbox mock 数据 seed（HTTP 或 `--direct`） |
| `test-instinct-inbox-e2e.sh` | Unix | Instinct Inbox API E2E（pytest）；UI 用 MCP chrome-devtools |
| `test-subagent-dashboard-e2e.sh` | Unix | Subagent Dashboard E2E — API prepare（delegate via agent-stream） |
| `subagent-dashboard-e2e-auth.mjs` | 双平台 | P2c E2E 共享 WebUI login + authenticated fetch |
| `subagent-dashboard-e2e-prepare.mjs` | 双平台 | P2c prepare：seed provider/YOLO、创建 chat、SSE delegate、GET `/subagents` 断言 → JSON |
| `subagent-dashboard-e2e-verify.mjs` | 双平台 | P2c verify：authenticated REST cancel 探测 subagent 已停止 |
| `lib/backend_bg.sh` | Unix | 后台启动 server（`dev.sh` / `start.sh` source） |
| `lib/` | Unix | 开发子脚本库目录，见 [lib/_ARCH.md](lib/_ARCH.md) |

## WebUI E2E（MCP chrome-devtools，禁止 @playwright/test）

产品 WebUI 端到端 UI 验收使用 **MCP chrome-devtools**（真实 Chrome 登录态 `:3000`），禁止 `@playwright/test` 与 pytest 无头浏览器。

| 脚本 | 职责 |
|------|------|
| `subagent-dashboard-e2e-prepare.mjs` | 登录 API、seed provider/YOLO、创建 chat、agent-stream delegate → JSON |
| `subagent-dashboard-e2e-verify.mjs` | UI cancel 后 REST 验证 subagent 已停止 |
| `test-subagent-dashboard-e2e.sh` | 确保 backend :8080 + 运行 prepare |
| `test-instinct-inbox-e2e.sh` | Instinct Inbox API pytest + seed-mock；UI 走 chrome-devtools |

环境变量：`E2E_UI_BASE`（默认 `http://127.0.0.1:3000`）、`E2E_API_BASE`（默认 `http://127.0.0.1:8080`）、`E2E_ADMIN_PASSWORD`。

## 依赖

- [scripts/lib/resolve_agent_root.sh](../lib/resolve_agent_root.sh) — 解析安装根目录
- [scripts/lib/start_server.sh](../lib/start_server.sh) — 后端进程启动
