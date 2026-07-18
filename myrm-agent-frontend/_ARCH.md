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
| CI | `frontend-build.yml` | `shared/**` 变更触发 line budget + strict TS + fractal docs + barrel policy + verify:i18n + remap vitest + `bun run build` + verify-sw-push |

## 脚本

详见 [scripts/_ARCH.md](scripts/_ARCH.md)。CI 核心：`check_fractal_docs.py`、`check_file_line_budget.py`、`check_typescript_strict.py`、`check_barrel_exports.py`、`verify-i18n.mjs`、`verify-sw-push.mjs`（`bun run build` 后）。

## PWA / Service Worker（Web 部署）

| 文件 | 职责 |
|------|------|
| `src/app/sw.ts` | Serwist SW 源：precache + Web Push（same-origin allowlist；open-tab pathname 匹配时 query 不同则 `client.navigate`） |
| `serwist.config.ts` | `next build` 后 `inject-manifest`（precache 清单来自 `.next`） |
| `public/sw.js` | 编译产物；生产由 `pwa-updater.tsx` 注册 `/sw.js`；dev/Tauri 不注册 |

构建：`bun run build` = i18n split → `next build`（`@serwist/next`）→ `build:sw-inject`（esbuild → `.serwist/sw-inject-src.js`）→ `serwist inject-manifest` → `verify-sw-push.mjs`。`build:tauri` 跳过 Serwist。

## 子模块

| 目录 | 文档 |
|------|------|
| `src/app/` | [src/app/_ARCH.md](src/app/_ARCH.md) |
| `src/components/` | [src/components/_ARCH.md](src/components/_ARCH.md) |
| `src/hooks/` | [src/hooks/_ARCH.md](src/hooks/_ARCH.md) |
| `src/store/` | [src/store/_ARCH.md](src/store/_ARCH.md) |
| `src/lib/` | [src/lib/_ARCH.md](src/lib/_ARCH.md) |
| `src/services/` | [src/services/_ARCH.md](src/services/_ARCH.md) |
| `src/i18n/` | [src/i18n/_ARCH.md](src/i18n/_ARCH.md) |
| `src/types/` | [src/types/_ARCH.md](src/types/_ARCH.md) |
| `src/__tests__/` | [src/__tests__/_ARCH.md](src/__tests__/_ARCH.md) |
| `scripts/` | [scripts/_ARCH.md](scripts/_ARCH.md) |

## 桶导出政策（SSOT）

三层规则；跨域门面由 `scripts/ci/barrel_whitelist.txt` 机读校验（`check_barrel_exports.py`）。

| 层 | 规则 |
|----|------|
| 跨域门面 | 仅 `scripts/ci/barrel_whitelist.txt` 列出的路径允许 `index.ts`；`components/features/**` 与 `components/error-boundary/index.ts` 另由脚本路径规则允许 |
| Feature 内 | `src/components/features/**/index.ts` 允许；子 `_ARCH.md` 登记职责 |
| 排除 | `src/i18n/index.ts` 为 `'use server'` cookie API，非 re-export barrel |

跨域白名单摘要：

| 路径 | 原因 |
|------|------|
| `hooks/tasks/index.ts` | WebSocket 任务订阅门面 |
| `store/memory/index.ts` | 记忆 store 类型再导出 |
| `store/skill/index.ts` | 技能 store 类型再导出 |
| `store/chat/types/index.ts` | 聊天域类型 barrel |
| `store/chat/messageStream/handlers/index.ts` | SSE handler 注册表 |
| `services/config/index.ts` | ConfigSync 公共 API（`@/services/config`） |
| `services/config/adapters/index.ts` | ConfigSync 适配器注册 |
| `services/file-service/index.ts` | 平台 FileService 单例 |
| `lib/intent-dispatcher/index.ts` | Slash/深链解析门面 |
| `components/layout/index.ts` | 布局门面（`PageLayout` 仍须直引，见 layout/_ARCH.md） |
| `components/error-boundary/index.ts` | 边界导出（layout 须直引 client 组件） |

`services/` 顶层单文件、`hooks/`（除 tasks）、`lib/`（除 intent-dispatcher）**禁止**新增 `index.ts`。

## 测试

| 层级 | 入口 | 说明 |
|------|------|------|
| 单元 | `bun run test` | Vitest + jsdom；**默认** colocated `src/**/__tests__/`；跨模块集成见 [src/__tests__/_ARCH.md](src/__tests__/_ARCH.md) |
| i18n | `bun run verify:i18n` | `pretest` 自动执行 |
| WebUI 集成 | MCP **chrome-devtools** | 真实 Chrome `:3000` 全链路；API prepare 见 `scripts/dev/*-e2e-*.mjs` |

**禁止** `@playwright/test` / `puppeteer` 无头浏览器 E2E（无 `tests/e2e/`、无 `playwright.config.ts`、无 CI Playwright 流水线）。Harness patchright 仅用于 server 浏览器自动化，不是 WebUI E2E 框架。
