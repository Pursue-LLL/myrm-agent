# scripts/ 模块架构

## 架构概述

开发/CI 脚本（非运行时）。Python 门禁与 Bun/Node 工具并存；CI 产物在 `scripts/ci/`。

## 文件清单

| 文件 | 职责 |
|------|------|
| `check_fractal_docs.py` | 分形 `_ARCH.md` 门禁（strict roots + recursive baseline）；禁止 `tsconfig.json` include 写入 `.next-isolated-*` |
| `check_file_line_budget.py` | TS/TSX 400 行预算门禁 |
| `check_typescript_strict.py` | `tsc --noEmit` strict 错误数门禁（`ci/typescript_strict_baseline.txt`；`tsconfig.json` `strict: true`） |
| `check_barrel_exports.py` | 跨域 `index.ts` 桶导出白名单门禁 |
| CI lockfile policy | `frontend-build.yml` 断言无 `package-lock.json`（bun.lock 为 SSOT） |
| `ci/fractal_docs_baseline.txt` | 递归扫描豁免目录（当前无条目） |
| `ci/file_line_budget_baseline.txt` | 存量超大文件豁免列表 |
| `ci/barrel_whitelist.txt` | 跨域 barrel 白名单（feature 内 barrel 由路径规则允许） |
| `verify-i18n.mjs` | 五语系 i18n 完整性 + SSR shell/deferred namespace 门禁 + `kanban` Chat↔Board closure keys（`pretest` + CI） |
| `verify-sw-push.mjs` | `public/sw.js` 须含 Web Push handler、URL 消毒、`resolvePushClientFocusAction`、`.navigate(`（`build:sw-inject` + Serwist inject-manifest + CI） |
| `build-sw-src.mjs` | esbuild 打包 `src/app/sw.ts` → `.serwist/sw-inject-src.js`（inject-manifest 入口，解析 lib import） |
| `scan-home-i18n-shell.mjs` | home-route `settings.*` 引用须在 SSR shell（CI via verify-i18n） |
| `verify-shell-i18n-runtime.mjs` | 运行时 SSR HTML / deferred API 校验（dev；shell 清单从 locale-manifest 解析） |
| `split-locale-namespaces.mjs` | 从 `locales/{lang}.json` 生成 `locales/namespaces/`（`dev.ts` / `build` / `build:tauri` / `prestart` / `pretest` 前置） |
| `sync_i18n.py` | 从 en 补全 ja/ko/de/zh（本地维护） |
| `dev.ts` | locale split + Next dev 入口（`dev` / `dev:lan` / `dev:clean`；`dev-server.lock` 健康跳过） |
| `dev-lock.ts` | dev lock 读写与 LISTEN 健康判定 |
| `port-cleanup.ts` | `:3000` LISTEN-only 清理 |
| `cleanup.ts` | 本地 dev 残留清理（`:3000` 进程、stale lock、非 active 的 `.next-isolated-*`、dev log truncate、stray `package-lock.json`） |
| `generate-artifact-types.ts` | 工件类型生成 |
| `export-known-sse-event-types.ts` | SSE 事件类型导出对齐 |
| `__tests__/` | 脚本相关单测 |

## 依赖

- 仓库根 `package.json` scripts 引用本目录
- `check_*` 由 CI `frontend-build.yml` 调用

## 约束

- 新 CI 门禁脚本放本目录并在本 `_ARCH.md` 与根 `_ARCH.md` CI 节登记
- baseline 文件仅通过 `--write-baseline` 更新，禁止手改豁免逻辑
- `ci/barrel_whitelist.txt` 跨域 barrel 条目须与根 `_ARCH.md` 桶表同步，手改后跑 `check_barrel_exports.py` 验证
