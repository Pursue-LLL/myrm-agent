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
| `verify-i18n.mjs` | 六语系 i18n 全量门禁：key parity（缺键=ERROR / 孤儿键=ERROR）、叶子类型一致、ICU 占位符变量一致、翻译壳检测（`collectTranslationShells` + 豁免见 `i18n-shell-allowlist.json`）、glossary forbidden（de/ko，`i18n-glossary.json`）、异常哨兵；另含 SSR shell/deferred namespace 门禁 + 关键 namespace keys（`pretest` + CI） |
| `verify-stable-mocks.mjs` | next-intl mock 稳定性门禁：扫描全部测试文件，硬拦截不稳定 mock（`useTranslations: () => (key) => ...` 箭头简写 / `() => { return (key) => ... }` 块体返回），防 Vitest OOM 复发（`lint` + `pretest` 前置） |
| `i18n-shell-core.mjs` | 翻译壳检测共享逻辑（`isLegitSameValue` / `collectTranslationShells` 等；verify-i18n 与 dump-remaining 共用，防 gate 口径漂移） |
| `i18n-patch-apply.mjs` | 将 `translation-patches/<locale>/*.json` 深度合并进 `locales/<locale>.json`（内容补齐工作流） |
| `i18n-build-patch.mjs` | 扁平 key→翻译 JSON 构建嵌套 `translation-patches` 补丁树 |
| `i18n-de-bulk-translate.py` | 从 en SSOT 批量机翻 de 剩余壳（Google Translate + placeholder 保护；缓存 `translation-patches/de/auto-translated-overrides.json`） |
| `i18n-de-apply-cache.py` | 将 `auto-translated-overrides.json` 回写到 `locales/de.json`（壳清零前的增量应用） |
| `i18n-de-fix-remaining.mjs` | de 收尾：认知词/渠道 Connect 文案壳 + glossary forbidden 键修正 |
| `i18n-dump-remaining.mjs` | 按 `i18n-shell-core.mjs` 同款壳检测逻辑导出某语言剩余翻译壳清单（TSV/JSON，支持 `--limit`/`--offset`/`--stats`） |
| `i18n-glossary.json` | Native QA 术语表 SSOT（de Sie-Form + ko 敬语约束与固定术语；`forbidden` 由 `verify-i18n.mjs` 强制执行） |
| `i18n-shell-allowlist.json` | 翻译壳检测豁免清单：真正不可翻译的值（品牌/凭据字段名/占位示例）与键路径 |
| `translation-patches/` | 各语言内容补齐补丁目录（`<locale>/batch-NN.json` 等嵌套 JSON 补丁，供 `i18n-patch-apply.mjs` 深度合并；应用前以 `i18n-dump-remaining.mjs` 导出剩余壳清单） |
| `verify-sw-push.mjs` | `public/sw.js` 须含 Web Push handler、URL 消毒、`resolvePushClientFocusAction`、`.navigate(`（`build:sw-inject` + Serwist inject-manifest + CI） |
| `build-sw-src.mjs` | esbuild 打包 `src/app/sw.ts` → `.serwist/sw-inject-src.js`（inject-manifest 入口，解析 lib import） |
| `scan-home-i18n-shell.mjs` | home-route `settings.*` 引用须在 SSR shell（CI via verify-i18n） |
| `verify-shell-i18n-runtime.mjs` | 运行时 SSR HTML / deferred API 校验（dev；shell 清单从 locale-manifest 解析） |
| `split-locale-namespaces.mjs` | 从 `locales/{lang}.json` 生成 `locales/namespaces/`（`dev.ts` / `build` / `build:tauri` / `prestart` / `pretest` 前置） |
| `sync_i18n.py` | 从 en（SSOT）补全其余 5 种语言缺失键（本地维护） |
| `dev.ts` | locale split + Next dev 入口（`dev` / `dev:lan` / `dev:clean`；`dev-server.lock` 健康跳过） |
| `dev-lock.ts` | dev lock 读写与 LISTEN 健康判定 |
| `port-cleanup.ts` | `:3000` LISTEN-only 清理 |
| `cleanup.ts` | 本地 dev 残留清理（`:3000` 进程、stale lock、非 active 的 `.next-isolated-*`、dev log truncate、stray `package-lock.json`、`strip_isolated_tsconfig.py`） |
| `strip_isolated_tsconfig.py` | 移除 Next isolated build 写入的 `tsconfig.json` include 与 `next-env.d.ts` 污染；重置 next-env 为 `.next/dev/types/routes.d.ts` + `root-params.d.ts`；E2E `release_runtime` teardown 与 `cleanup.ts` 调用 |
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
