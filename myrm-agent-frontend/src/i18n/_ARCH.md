# i18n/ 模块架构

## 架构概述

Next.js App Router 国际化：`next-intl` 路由与 cookie locale 读写。翻译 SSOT 在 `locales/{lang}.json`（zh/en/ja/ko/de/zh-TW）；`scripts/split-locale-namespaces.mjs` 生成 `locales/namespaces/` 供 shell/deferred 加载。

## 文件清单

| 文件 | 职责 |
|------|------|
| `config.ts` | 支持 locale 列表与 defaultLocale |
| `routing.ts` | next-intl routing 配置 |
| `request.ts` | Server Component locale 解析（`loadShellMessages`） |
| `load-messages.ts` | Server-only：shell / deferred namespace 文件加载 |
| `locale-manifest.ts` | SSR shell vs deferred namespace 清单（`SSR_SHELL_SETTINGS_SECTIONS` + deferred 顶层 `channels`） |
| `merge-messages.ts` | 浅合并 shell + deferred messages（settings 深合并） |
| `__tests__/locale-shell.test.ts` | shell/deferred 分割与 merge 单测 |
| `__tests__/ClientIntlProvider.test.tsx` | deferred fetch retry / fail-closed 单测 |
| `ClientIntlProvider.tsx` | mount 后 fetch `/api/i18n/deferred` 并 merge messages；失败 fail-closed + 指数 retry |
| `deferred-locale-context.tsx` | Settings 路由等待 deferred settings 加载后再渲染 |
| `index.ts` | `getLocale` / `setLocale`（cookie 读写） |
| `LocalizedProviders.tsx` | 根 i18n + 全局 initializer 树（Suspense 内） |
| `DocumentLang.tsx` | 客户端同步 `<html lang>` |

## 依赖

- `locales/namespaces/` — 运行时按需读取（由 `split-locale-namespaces.mjs` 生成，gitignore）
- `@/lib/utils/localeUtils` — `NEXT_LOCALE_COOKIE_NAME`、`negotiateLocale`
- 根 `middleware.ts` — 营销站 `?locale=` 写 cookie + 首次 Accept-Language 自动检测写 cookie
- `@/components/layout/PageLayout` — shell-first 页面壳

## 首次访问 Locale 自动检测

首次访问无 `NEXT_LOCALE` cookie 时，`middleware.ts` 通过 `negotiateLocale()` 解析 `Accept-Language` header（RFC 7231 §5.3.5 quality-factor），匹配 `locales` 列表后写入 cookie。无匹配时回退 `'en'`（国际默认），覆盖 WebUI / Cloud / Tauri 三部署场景。`layout.tsx` 通过 `getLocale()` 动态设置 `<html lang>`，`DocumentLang` 在客户端同步。

## 约束

- UI 文案禁止硬编码；使用 `useTranslations` + `locales/`

## 首屏体积（prod `next start`，2026-07-13 实测）

| 指标 | 优化前（历史） | 当前 prod |
|------|----------------|-----------|
| HTML transfer | ~943KB | ~447KB |
| TTFB | 120–430ms | ~105ms |
| SSR `MISSING_MESSAGE` | — | 无（memory 在 shell） |

deferred 顶层 namespace 仅 `channels`；`memory` 必须在 SSR shell（`ChatWindow` 等首屏组件引用）。
home-route `settings.*` 引用必须通过 `scripts/scan-home-i18n-shell.mjs`（CI 在 verify-i18n 内执行）。
