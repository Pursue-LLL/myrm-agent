# tests/e2e/ Playwright E2E

## 架构概述

产品 WebUI 端到端测试。依赖本地 backend `:8080` + frontend `:3000`（或 `PLAYWRIGHT_SKIP_WEBSERVER=1`）。

## 环境变量

| 变量 | 用途 |
|------|------|
| `PLAYWRIGHT_BASE_URL` | 前端根 URL，默认 `http://127.0.0.1:3000` |
| `PLAYWRIGHT_API_BASE` | 后端 API，默认 `http://127.0.0.1:8080` |
| `PLAYWRIGHT_RUN_INSTINCT_INBOX_E2E` | 启用 `instinct-inbox.spec.ts` |
| `PLAYWRIGHT_RUN_SUBAGENT_DASHBOARD_E2E` | 启用 `subagent-dashboard.spec.ts`（需 `BASIC_API_KEY` + `BASIC_MODEL`） |
| `PLAYWRIGHT_SKIP_WEBSERVER` | `1` 时不启动 webServer，使用已运行实例 |

## Spec 清单

| 文件 | 职责 |
|------|------|
| `instinct-inbox.spec.ts` | Agent 洞察 tab：clone → `seed-mock?agent_id=` → approve/dismiss（**不 mock `/approvals`**） |
| `subagent-dashboard.spec.ts` | 聊天 delegate → Subagent Dashboard → cancel（`PLAYWRIGHT_RUN_SUBAGENT_DASHBOARD_E2E=1` + `.env.test` LLM） |
| `helpers/auth.ts` | 登录与 setup 状态 |
| `helpers/seedE2eProviders.ts` | 从 `BASIC_*` 注入 WebUI provider 配置（deviceId=`tauri-local`，与 TauriConfigAdapter 一致） |
| `helpers/subagentDashboardE2e.ts` | 预置 ephemeral `test_bash` chat + 轮询 subagent REST |

## CI

`myrm-agent/scripts/ci/run_frontend_e2e.sh`
