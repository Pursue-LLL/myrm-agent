# app/ (Next.js App Router)

## 架构概述

路由薄壳：布局在 `layout.tsx`，业务 UI 在 `@/components/features/*`。动态段 `[chatId]`、`settings/[tab]` 等仅做参数传递与鉴权包装。

## 路由分组

| 路径                                                   | 职责                                                                                                                                                                   | 模式            |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| `/`, `/chat`, `/[chatId]`, `/chat/[chatId]`            | 主对话（`/chat/:chatId` 经 `next.config.ts` rewrite 指向 `/:chatId` 保证测试与深链兼容）                                                                               | 全模式          |
| `/settings`, `/settings/[tab]`                         | 设置页（`SETTINGS_TAB_REDIRECTS` 别名服务端重定向，如 `persona→personalization`）                                                                                            | 全模式          |
| `/auth/login`, `/auth/setup`                           | WebUI 本地管理员                                                                                                                                                       | local / desktop |
| `/auth/oauth/callback`                                 | CP OAuth；回跳的 `redirect` 值携带 `desktop=1&state` 时不在浏览器兑换，经深链把 exchange+state 交回桌面端                                                                                                                   | SaaS 构建+桌面  |
| `/intent/*`                                            | Web/SaaS Deep Link 落地页（`ask/chat/agent/oauth/install-skill`），交由 `IntentDispatcher` 解析并跳转；避免 `/intent/...` 404；详见 [intent/_ARCH.md](intent/_ARCH.md) | 全模式          |
| `/work`                                                | 多窗格并行工作区（原 `/workspace`，301 重定向）                                                                                                                        | 全模式          |
| `/projects`                                            | Projects Dashboard 聚合入口（Kanban / Cron / Artifacts）                                                                                                               | 全模式          |
| `/library`, `/brain`                                   | 资料库                                                                                                                                                                 | 全模式          |
| `/kanban`, `/artifacts`, `/cron` 等                    | 功能页（通过 Projects Dashboard 聚合访问）                                                                                                                             | 全模式          |
| `/journey`                                             | 学习旅程统一页（成长仪表盘 + 知识图谱 + 技能趋势）                                                                                                                     | 全模式          |
| `/growth`                                              | 301 重定向 → `/journey`                                                                                                                                                | 全模式          |
| `/pricing`, `/subscription`, `/payment/*`              | 计费与订阅                                                                                                                                                             | SaaS 为主       |
| `/api/*`                                               | Next Route Handlers（代理、checkout、`/api/i18n/deferred` 客户端 deferred locale）                                                                                     | 按路由          |

## Service Worker（Web PWA）

| 文件    | 地位 | 职责                                                                                                                                            | I/O/P |
| ------- | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `sw.ts` | 核心 | Serwist SW 源：precache + API runtime cache + Web Push 显示/点击（same-origin URL allowlist；已开 Tab 同 path 不同 query 时 `client.navigate`） | ✅    |

编译产物 `public/sw.js` 由 `scripts/build-sw-src.mjs` + 根目录 `serwist.config.ts` + `bun run build` 生成；注册见 `@/components/features/app-shell/pwa-updater.tsx`（生产 Web only；dev 注销 SW；Tauri skip）。

## 依赖

- `@/components/features/app-shell` — 全局初始化
- `@/store/useAuthStore` — 路由守卫

## Locale 接力

营销站 `?locale=` 由根目录 `middleware.ts` 写 `NEXT_LOCALE` cookie（非 `app/` 路由内处理）。

## 约束

- 新页面优先复用 `features/` 组件，不在 `app/` 堆业务逻辑。
- 单文件 page >600 行应下沉到 `features/`（如 `batch-directories/page.tsx`）。
- `layout.tsx`：构建期静态 `metadata`（`lib/metadata/static-metadata.ts`）；`<body suppressHydrationWarning>` 压制浏览器扩展注入属性导致的 hydration warning；`LocalizedProviders` 仍在 Suspense 内（cookie locale）。
- `focus-ring.css`（由 `globals.css` 引入）：键盘焦点环基线，只作用于自身无 `focus`/`focus-visible` 样式的可交互元素（`@layer base`，任何 Tailwind utility 与组件样式都可覆盖；不匹配文本输入）；复用主题 token `--ring`，鼠标/触摸不触发。 组件若写 `outline-none` 就会覆盖它，须自带 `focus-visible:ring-*`，由 `scripts/check-a11y-ratchet.mjs`（`focus-visibility-scan.ts`）在 lint 阶段强制。
- `globals.css` 的 `@media (prefers-reduced-motion: reduce)` 通用选择器块：全局兜底，把全站 CSS 动画与过渡压到瞬时（`0.01ms` + `animation-iteration-count: 1`，`scroll-behavior: auto`），组件层不需要逐个处理。刻意不用 `animation: none`——瞬时收尾仍会派发 `animationend`，依赖它决定卸载时机的浮层才能照常收场；`none` 会让浮层判断不到动画而提前卸载。framer-motion 走 Web Animations API、CSS 覆盖不到，由 `PageLayout.tsx` 的 `<MotionConfig reducedMotion="user">` 负责（位置类动画瞬时、透明度淡出保留）。两个守卫分别由 `src/app/__tests__/reduced-motion-safety-net.test.ts` 与 `src/components/layout/__tests__/PageLayout.test.tsx` 钉住。

## globals.css

- 产品界面统一关闭 `backdrop-filter`（`[class*='backdrop-blur']` 覆盖）：实测同页 GPU 69% → 38%，深色半透明底色已足够可读；新增玻璃质感请用更实的底色而不是模糊。
- 表面语义：暗色 `--card` 由 `color-mix(background 94%, foreground 6%)` 派生、`--popover` 取 88%/12%，亮色两者取纯白；`--muted-foreground` 统一取 `foreground 60%`（暗色实测 7.08:1、亮色 5.22:1）。均由主题 token 派生，新增主题/art 组合无需逐个补色值；不要在组件里写死近黑/近白。

- 字体：`app/fonts.ts` 通过 `next/font/local` 自托管 `src/assets/fonts/InterVariable-latin.woff2`（OFL，400–600，47KB，预载）与 `AtkinsonVariable-latin.woff2`（OFL，400–700，33KB，按需）；`--font-sans` 以 `var(--font-inter, ui-sans-serif)` 开头，Atkinson 主题通过 `var(--font-atkinson)` 覆盖。构建、运行时与桌面打包都不依赖外网，CJK 按字形回退 PingFang/Noto。