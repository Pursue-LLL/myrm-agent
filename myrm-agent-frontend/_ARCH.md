# myrm-agent-frontend 模块架构

## 架构概述

Next.js 16 WebUI。与 `myrm-agent-server` 同处 monorepo，可引用根目录 `shared/` 静态配置。

## Monorepo 构建契约

| 项 | 配置 | 说明 |
|----|------|------|
| `@shared/*` | `tsconfig.json` paths + `next.config.ts` | 指向 `../shared/*` |
| `turbopack.root` | monorepo 根（`myrm-agent/`） | dev/build 解析跨包 JSON |
| `outputFileTracingRoot` | monorepo 根 | standalone/Tauri 打包 trace |
| Docker build | [Dockerfile](Dockerfile) | builder 布局 `/app/frontend` + `/app/shared`（context = `myrm-agent/` 根） |
| CI | `frontend-build.yml` | `shared/**` 变更触发 line budget + verify:i18n + remap vitest + `next build` |

## 脚本

| 文件 | 职责 |
|------|------|
| `scripts/check_file_line_budget.py` | TS/TSX 400 行预算 CI（baseline 在 `scripts/ci/file_line_budget_baseline.txt`） |
| `scripts/check_fractal_docs.py` | 分形 `_ARCH.md` 门禁（strict roots + recursive baseline 在 `scripts/ci/fractal_docs_baseline.txt`） |
| `scripts/verify-i18n.mjs` | 五语系 i18n 完整性校验（`bun run verify:i18n`；CI 与 `pretest` 共用） |
| `scripts/sync_i18n.py` | 从 en 递归补全 ja/ko/de/zh 缺失 key（本地维护用） |
| `scripts/dev.ts` | Next.js dev 入口；健康时跳过 port kill（`dev-server.lock` + HTTP 200） |
| `scripts/dev-lock.ts` | `dev-server.lock` 读写；健康检查沿进程祖先链判定监督进程拥有 LISTEN |
| `scripts/port-cleanup.ts` | `:3000` LISTEN-only 清理（不杀 Chrome ESTABLISHED 客户端） |

## 子模块

| 目录 | 文档 |
|------|------|
| `src/app/` | [src/app/_ARCH.md](src/app/_ARCH.md) |
| `src/components/` | [src/components/_ARCH.md](src/components/_ARCH.md) |
| `src/hooks/` | [src/hooks/_ARCH.md](src/hooks/_ARCH.md) |
| `src/store/` | [src/store/_ARCH.md](src/store/_ARCH.md) |
| `src/lib/` | [src/lib/_ARCH.md](src/lib/_ARCH.md) |
| `src/services/` | [src/services/_ARCH.md](src/services/_ARCH.md) |

## 测试

| 层级 | 入口 | 说明 |
|------|------|------|
| 单元 | `bun run test` | Vitest + jsdom（`src/**/__tests__`） |
| i18n | `bun run verify:i18n` | `pretest` 自动执行 |
| WebUI 集成 | MCP **chrome-devtools** | 真实 Chrome `:3000` 全链路；API prepare 见 `scripts/dev/*-e2e-*.mjs` |

**禁止** `@playwright/test` / `puppeteer` 无头浏览器 E2E（无 `tests/e2e/`、无 `playwright.config.ts`、无 CI Playwright 流水线）。Harness patchright 仅用于 server 浏览器自动化，不是 WebUI E2E 框架。
