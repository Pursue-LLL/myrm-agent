# i18n/ 模块架构

## 架构概述

Next.js App Router 国际化：`next-intl` 路由与 cookie locale 读写。文案 SSOT 在仓库根 `locales/*.json`。

## 文件清单

| 文件 | 职责 |
|------|------|
| `config.ts` | 支持 locale 列表与 defaultLocale |
| `routing.ts` | next-intl routing 配置 |
| `request.ts` | Server Component locale 解析 |
| `index.ts` | `getLocale` / `setLocale`（cookie 读写） |

## 依赖

- `@/lib/utils/localeUtils` — `NEXT_LOCALE_COOKIE_NAME`
- 根 `middleware.ts` — 营销站 `?locale=` 写 cookie

## 约束

- UI 文案禁止硬编码；使用 `useTranslations` + `locales/`
