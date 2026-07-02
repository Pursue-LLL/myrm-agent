# tests/e2e/ Playwright E2E

## 架构概述

产品 WebUI 端到端测试。依赖本地 backend `:8080` + frontend `:3000`（或 `PLAYWRIGHT_SKIP_WEBSERVER=1`）。

## 环境变量

| 变量 | 用途 |
|------|------|
| `PLAYWRIGHT_BASE_URL` | 前端根 URL，默认 `http://127.0.0.1:3000` |
| `PLAYWRIGHT_API_BASE` | 后端 API，默认 `http://127.0.0.1:8080` |
| `PLAYWRIGHT_RUN_INSTINCT_INBOX_E2E` | 启用 `instinct-inbox.spec.ts` |
| `PLAYWRIGHT_SKIP_WEBSERVER` | `1` 时不启动 webServer，使用已运行实例 |

## Spec 清单

| 文件 | 职责 |
|------|------|
| `instinct-inbox.spec.ts` | Agent 洞察 tab：clone → `seed-mock?agent_id=` → approve/dismiss（**不 mock `/approvals`**） |
| `helpers/auth.ts` | APIRequestContext 登录与 setup 状态 |
| `helpers/ensureWebUiBrowserSession.ts` | 浏览器 origin (:3000) 登录 + onboarding |
| `helpers/prepareChatPageForE2e.ts` | dismiss migration banner + 等 chat send 可点 |
| `helpers/seedE2eProviders.ts` | 从 `BASIC_*` 注入 WebUI provider + YOLO security（deviceId=`tauri-local`） |

## Subagent Dashboard E2E（chrome-devtools，非 Playwright）

P2c 流程：**API prepare** + **MCP chrome-devtools** 操作本机已登录 Chrome（`:3000`）。

| 脚本 | 职责 |
|------|------|
| `myrm-agent/scripts/dev/subagent-dashboard-e2e-prepare.mjs` | 登录 API、seed provider/YOLO、创建 chat、agent-stream delegate → 输出 `{ chatId, taskId, treeRow, uiUrl }` |
| `myrm-agent/scripts/dev/subagent-dashboard-e2e-verify.mjs` | UI cancel 后 REST 验证 subagent 已停止 |
| `myrm-agent/scripts/dev/test-subagent-dashboard-e2e.sh` | 确保 backend :8080 + 运行 prepare |

Agent 在 UI 阶段使用 **MCP chrome-devtools**（真实 Chrome 登录态），禁止 `@playwright/test` 与 pytest 无头浏览器。

## CI

`myrm-agent/scripts/ci/run_frontend_e2e.sh` — 默认不跑 Subagent Dashboard（走 chrome-devtools 手工/MCP 流程）。本地 prepare：`myrm-agent/scripts/dev/test-subagent-dashboard-e2e.sh`。
