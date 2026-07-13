# app/ (Next.js App Router)

## 架构概述

路由薄壳：布局在 `layout.tsx`，业务 UI 在 `@/components/features/*`。动态段 `[chatId]`、`settings/[tab]` 等仅做参数传递与鉴权包装。

## 路由分组

| 路径 | 职责 | 模式 |
|------|------|------|
| `/`, `/chat`, `/[chatId]` | 主对话 | 全模式 |
| `/settings`, `/settings/[tab]` | 设置页（`DEPRECATED_TAB_MAP` 别名永久重定向，如 `persona→personalization`） | 全模式 |
| `/auth/login`, `/auth/setup` | WebUI 本地管理员 | local / desktop |
| `/auth/oauth/callback` | CP OAuth | SaaS 构建 |
| `/work` | 多窗格并行工作区（原 `/workspace`，301 重定向） | 全模式 |
| `/projects` | Projects Dashboard 聚合入口（Kanban / Cron / Artifacts） | 全模式 |
| `/library`, `/brain` | 资料库 | 全模式 |
| `/kanban`, `/artifacts`, `/cron` 等 | 功能页（通过 Projects Dashboard 聚合访问） | 全模式 |
| `/journey` | 学习旅程统一页（成长仪表盘 + 知识图谱 + 技能趋势） | 全模式 |
| `/growth` | 301 重定向 → `/journey` | 全模式 |
| `/skill-optimization` | 技能优化 A/B 对比页（`skill-optimization/page.tsx`，e2e 覆盖） | 全模式 |
| `/batch-optimization`, `/batch-optimization/[batchId]` | 批量技能优化列表与详情 — 见 [batch-optimization/_ARCH.md](batch-optimization/_ARCH.md) | 全模式 |
| `/pricing`, `/subscription`, `/payment/*` | 计费与订阅 | SaaS 为主 |
| `/api/*` | Next Route Handlers（代理、checkout） | 按路由 |

## 依赖

- `@/components/features/app-shell` — 全局初始化
- `@/store/useAuthStore` — 路由守卫

## Locale 接力

营销站 `?locale=` 由根目录 `middleware.ts` 写 `NEXT_LOCALE` cookie（非 `app/` 路由内处理）。

## 约束

- 新页面优先复用 `features/` 组件，不在 `app/` 堆业务逻辑。
- 单文件 page >600 行应下沉到 `features/`（如 `batch-optimization/page.tsx`）。
- `layout.tsx`：构建期静态 `metadata`（`lib/metadata/static-metadata.ts`）；`<body suppressHydrationWarning>` 压制浏览器扩展注入属性导致的 hydration warning；`LocalizedProviders` 仍在 Suspense 内（cookie locale）。
