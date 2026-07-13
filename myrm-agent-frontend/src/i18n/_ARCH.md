# i18n/ 模块架构

## 架构概述

Next.js App Router 国际化：`next-intl` 路由与 cookie locale 读写。翻译 SSOT 在 `locales/{lang}.json`；`scripts/split-locale-namespaces.mjs` 生成 `locales/namespaces/` 供 shell/deferred 加载。

## 文件清单

| 文件 | 职责 |
|------|------|
| `config.ts` | 支持 locale 列表与 defaultLocale |
| `routing.ts` | next-intl routing 配置 |
| `request.ts` | Server Component locale 解析（shell namespaces + settings.menu SSR） |
| `load-messages.ts` | Server-only：shell / deferred namespace 文件加载 |
| `locale-manifest.ts` | SSR shell vs deferred namespace 清单 |
| `LazyLocaleHydrator.tsx` | mount 后 fetch `/api/i18n/deferred` 并 merge messages |
| `index.ts` | `getLocale` / `setLocale`（cookie 读写） |
| `LocalizedProviders.tsx` | 根 i18n + 全局 initializer 树（Suspense 内） |
| `DocumentLang.tsx` | 客户端同步 `<html lang>` |

## 依赖

- `locales/namespaces/` — 运行时按需读取（由 `split-locale-namespaces.mjs` 生成，gitignore）
- `@/lib/utils/localeUtils` — `NEXT_LOCALE_COOKIE_NAME`
- 根 `middleware.ts` — 营销站 `?locale=` 写 cookie
- `@/components/layout/PageLayout` — shell-first 页面壳

## 约束

- UI 文案禁止硬编码；使用 `useTranslations` + `locales/`
