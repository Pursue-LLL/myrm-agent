# i18n/ 模块架构

## 架构概述

Next.js App Router 国际化：`next-intl` 路由与 cookie locale 读写。文案 SSOT 在仓库根 `locales/*.json`。Cookie locale 在 `LocalizedProviders` 内于 Suspense 边界读取，满足 Next.js 16.3 cacheComponents 即时导航约束。

## 文件清单

| 文件 | 职责 |
|------|------|
| `config.ts` | 支持 locale 列表与 defaultLocale |
| `routing.ts` | next-intl routing 配置 |
| `request.ts` | Server Component locale 解析 |
| `index.ts` | `getLocale` / `setLocale`（cookie 读写） |
| `LocalizedProviders.tsx` | 根 i18n + 全局 initializer 树（Suspense 内） |
| `DocumentLang.tsx` | 客户端同步 `<html lang>` |

## 依赖

- `@/lib/utils/localeUtils` — `NEXT_LOCALE_COOKIE_NAME`
- 根 `middleware.ts` — 营销站 `?locale=` 写 cookie
- `@/components/layout/PageLayout` — shell-first 页面壳

## 约束

- UI 文案禁止硬编码；使用 `useTranslations` + `locales/`
