# myrm-agent-frontend 模块架构

## 架构概述

Next.js 16 WebUI。与 `myrm-agent-server` 同处 monorepo，可引用根目录 `shared/` 静态配置。

## Monorepo 构建契约

| 项 | 配置 | 说明 |
|----|------|------|
| `@shared/*` | `tsconfig.base.json` paths + `next.config.ts` | 指向 `../shared/*`（`tsconfig.json` 经 `extends` 继承） |
| `tsconfig` 分层（**不可合并**） | `tsconfig.json`（`extends` + `include`）· `tsconfig.base.json`（`compilerOptions`） | `compilerOptions` **必须**留在 base：Next 的 `writeConfigurationDefaults` 在检测到 `extends` 时会直接跳过配置重写，这正是隔离 lane（`MYRM_NEXT_DIST_DIR=.next-isolated-*`）无法再把 lane 路径写进被 git 追踪的 `tsconfig.json` 的原因。把 `compilerOptions` 合回根文件会立刻让门禁瞬态假红与脏 glob 入库复发 |
| `locales` include 范围（**必须是 `locales/*.json`**） | `tsconfig.json` `include` | 只纳入 6 个**被 git 追踪**的顶层 locale。**禁止**改回 `locales/**/*.json`：`locales/namespaces/` 是 .gitignore 忽略的生成目录（3157+ 文件，i18n 脚本持续写入），全量 glob 会让 `check_typescript_strict.py` 在生成中途命中 `TS6053 File not found`，被无差别计数当成真实类型错误，导致门禁随机假红。`src/**` 对所需 namespace JSON 的静态 import 仍会被 TS 自动纳入，故无覆盖面损失 |
| `turbopack.root` | monorepo 根（`myrm-agent/`） | dev/build 解析跨包 JSON |
| `outputFileTracingRoot` | monorepo 根 | standalone/Tauri 打包 trace |
| Docker build | [Dockerfile](Dockerfile) | builder 布局 `/app/frontend` + `/app/shared`（context = `myrm-agent/` 根） |
| 依赖版本约束 | `package.json` `overrides` · `devDependencies.vite` | `overrides` 只收「第三方包用精确版本固定了带漏洞的版本，且该包的最新发布仍未修复」的依赖：`monaco-editor` 固定 `dompurify`、`@serwist/*` 固定 `zod`；覆盖后嵌套副本与直接依赖收敛到同一个已修复版本，上游发布修复后删掉对应条目。`overrides` 不作用于 peer 依赖，所以 `vitest` 的 peer `vite`（范围含 8.x）显式声明在 `devDependencies`，固定在 7.x 的已修复版本。其余传递依赖的漏洞靠刷新 `bun.lock` 解决，不加 override |
| CI | `frontend-build.yml` | `myrm-agent-frontend/**` / `shared/**` 变更触发：先 `bun run i18n:split` 生成 gitignored 的 `locales/namespaces/`，其后 lint 门禁（`bun run lint`：oxlint 与七道静态门禁）+ strict TS + fractal docs + 孤儿模块（相对对照点无新增）+ barrel policy + module resolution + verify:i18n + remap vitest + `bun run build`（末段含 verify-sw-push）互相独立执行（单个红灯不掩盖其余，一次运行列出全部失败门禁） |

## 脚本

详见 [scripts/_ARCH.md](scripts/_ARCH.md)。CI 核心：`oxlint`（errors 阻断 / warnings 不阻断，配置 `.oxlintrc.json` + `.oxlintignore`；`bun run lint` 经 `scripts/run-lint-gates.ts` 把 `verify:stable-mocks` / `verify:a11y` / `verify:theme-colors` / `verify:reduced-motion` / `verify:hardcoded-copy` / `verify:icu-syntax` / `verify:intl-options` 七道静态门禁与 oxlint 全部执行并汇总失败项；`verify:hardcoded-copy` 只统计从产品入口可达的文件，孤儿模块由孤儿门禁管）、`check_fractal_docs.py`、`check_typescript_strict.py`、`check_barrel_exports.py`、`check_module_resolution.py`、`check-orphan-modules.mjs`（CI 带 `--base`，只拦相对对照点新增的孤儿；`bun run verify:orphans` 手动盘点存量）、`verify-i18n.mjs`、`verify-sw-push.mjs`（`bun run build` 末段执行）。tsc 与 `check_module_resolution.py` 依赖 `locales/namespaces/` 生成物，CI 与 `dev` / `pretest` 一样先跑 `i18n:split`。

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
| 跨域门面 | 仅 `scripts/ci/barrel_whitelist.txt` 列出的路径允许 `index.ts`；`components/features/**` 另由脚本路径规则允许 |
| Feature 内 | `src/components/features/**/index.ts` 允许；子 `_ARCH.md` 登记职责 |
| 排除 | `src/i18n/index.ts` 为 `'use server'` cookie API，非 re-export barrel |

跨域白名单摘要：

| 路径 | 原因 |
|------|------|
| `store/memory/index.ts` | 记忆 store 类型再导出 |
| `store/skill/index.ts` | 技能 store 类型再导出 |
| `store/chat/types/index.ts` | 聊天域类型 barrel |
| `store/chat/messageStream/handlers/index.ts` | SSE handler 注册表 |
| `services/config/index.ts` | ConfigSync 公共 API（`@/services/config`） |
| `services/config/adapters/index.ts` | ConfigSync 适配器注册 |
| `services/file-service/index.ts` | 平台 FileService 单例 |
| `lib/humanize/index.ts` | 人化文案门面 |
| `lib/intent-dispatcher/index.ts` | Slash/深链解析门面 |
| `lib/desktop-bridge/index.ts` | 桌面桥接门面 |
| `theme-engine/index.ts` | 主题引擎门面 |

`services/` 顶层单文件、`hooks/`、`lib/`（除 intent-dispatcher / humanize / desktop-bridge）**禁止**新增 `index.ts`。

## 测试

| 层级 | 入口 | 说明 |
|------|------|------|
| 单元 | `bun run test` | Vitest + jsdom；**默认** colocated `src/**/__tests__/`；跨模块集成见 [src/__tests__/_ARCH.md](src/__tests__/_ARCH.md) |
| i18n | `bun run verify:i18n` | `pretest` 自动执行 |
| WebUI 集成 | MCP **chrome-devtools** | 真实 Chrome `:3000` 全链路；API prepare 见 `scripts/dev/*-e2e-*.mjs` |

**禁止** `@playwright/test` / `puppeteer` 无头浏览器 E2E（无 `tests/e2e/`、无 `playwright.config.ts`、无 CI Playwright 流水线）。Harness patchright 仅用于 server 浏览器自动化，不是 WebUI E2E 框架。
