# app/ (Next.js App Router)

## 架构概述

路由薄壳：布局在 `layout.tsx`，业务 UI 在 `@/components/features/*`。动态段 `[chatId]`、`settings/[tab]` 等仅做参数传递与鉴权包装。

## 路由分组

| 路径 | 职责 | 模式 |
|------|------|------|
| `/`, `/chat`, `/[chatId]` | 主对话 | 全模式 |
| `/settings`, `/settings/[tab]` | 设置页 | 全模式 |
| `/auth/login`, `/auth/setup` | WebUI 本地管理员 | local / desktop |
| `/auth/oauth/callback` | CP OAuth | SaaS 构建 |
| `/workspace`, `/library`, `/brain` | 工作区 / 资料库 | 全模式 |
| `/kanban`, `/artifacts`, `/cron` 等 | 功能页 | 全模式 |
| `/pricing`, `/subscription`, `/payment/*` | 计费与订阅 | SaaS 为主 |
| `/api/*` | Next Route Handlers（代理、checkout） | 按路由 |

## 依赖

- `@/components/features/app-shell` — 全局初始化
- `@/store/useAuthStore` — 路由守卫

## 约束

- 新页面优先复用 `features/` 组件，不在 `app/` 堆业务逻辑。
- 单文件 page >600 行应下沉到 `features/`（如 `batch-optimization/page.tsx`）。
