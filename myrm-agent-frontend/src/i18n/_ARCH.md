# i18n/ 模块架构

## 架构概述

Next.js App Router 国际化：`next-intl` 路由与 cookie locale 读写。翻译 SSOT 在 `locales/{lang}.json`（zh/en/ja/ko/de/zh-TW）；`scripts/split-locale-namespaces.mjs` 生成 `locales/namespaces/` 供 shell/deferred 加载。

## 文件清单

| 文件                                    | 职责                                                                                              |
| --------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `config.ts`                             | 支持 locale 列表与 defaultLocale                                                                  |
| `routing.ts`                            | next-intl routing 配置                                                                            |
| `request.ts`                            | Server Component locale 解析（`loadShellMessages`）                                               |
| `load-messages.ts`                      | Server-only：shell / deferred namespace 文件加载                                                  |
| `locale-manifest.ts`                    | SSR shell vs deferred namespace 清单（含 `themeStudio` settings shell；deferred 顶层 `channels`） |
| `merge-messages.ts`                     | 浅合并 shell + deferred messages（settings 深合并）                                               |
| `__tests__/locale-shell.test.ts`        | shell/deferred 分割与 merge 单测                                                                  |
| `__tests__/ClientIntlProvider.test.tsx` | deferred fetch retry / fail-closed 单测                                                           |
| `ClientIntlProvider.tsx`                | mount 后 fetch `/api/i18n/deferred` 并 merge messages；失败 fail-closed + 指数 retry              |
| `deferred-locale-context.tsx`           | Settings 路由等待 deferred settings 加载后再渲染                                                  |
| `index.ts`                              | `getLocale` / `setLocale`（cookie 读写）                                                          |
| `LocalizedProviders.tsx`                | 根 i18n + 全局 initializer 树（Suspense 内）                                                      |
| `DocumentLang.tsx`                      | 客户端同步 `<html lang>`                                                                          |

## 依赖

- `locales/namespaces/` — 运行时按需读取（由 `split-locale-namespaces.mjs` 生成，gitignore）
- `@/lib/utils/localeUtils` — `NEXT_LOCALE_COOKIE_NAME`、`negotiateLocale`
- 根 `middleware.ts` — 营销站 `?locale=` 写 cookie + 首次 Accept-Language 自动检测写 cookie
- `@/components/layout/PageLayout` — shell-first 页面壳

## 首次访问 Locale 自动检测

首次访问无 `NEXT_LOCALE` cookie 时，`middleware.ts` 通过 `negotiateLocale()` 解析 `Accept-Language` header（RFC 7231 §5.3.5 quality-factor），匹配 `locales` 列表后写入 cookie。无匹配时回退 `'en'`（国际默认），覆盖 WebUI / Cloud / Tauri 三部署场景。`layout.tsx` 通过 `getLocale()` 动态设置 `<html lang>`，`DocumentLang` 在客户端同步。

## 约束

- UI 文案禁止硬编码；使用 `useTranslations` + `locales/`
- `locales/{lang}.json` 必须是合法 JSON；`pretest` / `build` 首步 `i18n:split` 会对 SSOT 执行 `JSON.parse`
- Security Profile 委派权限 UI 文案键（6 语言 parity 由 `verify:i18n` 强制）：`settings.securityPolicy.permissionTypes`、`settings.securityPolicy.delegationPermissionsGuide`（含 `bindingHint` 子智能体绑定导航）

## 首屏体积（prod `next start`，2026-07-13 实测）

| 指标                  | 优化前（历史） | 当前 prod             |
| --------------------- | -------------- | --------------------- |
| HTML transfer         | ~943KB         | ~447KB                |
| TTFB                  | 120–430ms      | ~105ms                |
| SSR `MISSING_MESSAGE` | —              | 无（memory 在 shell） |

deferred 顶层 namespace 仅 `channels`；`memory` 必须在 SSR shell（`ChatWindow` 等首屏组件引用）。
home-route `settings.*` 引用必须通过 `scripts/scan-home-i18n-shell.mjs`（CI 在 verify-i18n 内执行）。
i18n 质量门禁（`bun run verify:i18n`）：en 为唯一 SSOT，各语言必须与 en 键全集一致、叶子类型一致、ICU 占位符变量一致，且不得存在「与英文相同的翻译壳」（豁免清单 `scripts/i18n-shell-allowlist.json`；壳检测逻辑 SSOT 在 `scripts/i18n-shell-core.mjs`）。
代码引用门禁（`scripts/verify-i18n-references.mjs`，随 `verify:i18n` 执行）：静态扫描 `src/**\/*.{ts,tsx}` 的 `t()` 引用，按最近前驱同名翻译绑定归因命名空间，逐一校验 en.json（SSOT）键存在；调用位于同名绑定声明之前（helper 前置定义、t 由组件体传入）时退化为「同名绑定命名空间并集」验证（任一候选存在即通过）；无同名绑定文件（props/参数传入 t）的盲区治理：解析真实 import 引用链 + 调用点实参推导（调用方把翻译绑定作为实参/JSX 属性传给当前模块时直接采用其命名空间），再沿 import 引用链 BFS 递归向上归因（seen 防环、无固定深度上限，兼容多级 helper 转发链），防漏检根 `t('error')`、`memory.enabled` 类真实缺失；动态命名空间绑定（`useTranslations(<变量>)`）运行时命名空间由调用方决定，无法静态归因，与动态 key 同理跳过（不得递归继承，避免误归因到调用方其他翻译绑定）；`showI18nToast` 的 `titleKey`/options 中 `descriptionKey`/`action.label` 为完整键引用，独立于命名空间归因直接校验（三元 descriptionKey/action.label 分支由专用正则提取）；所有 `t()` 调用一律纳入检查——`{ fallback: 'x' }` 是插值对象而非 next-intl 兜底（translateFn 第 4 位置参数才是 fallback），不得假跳过——补 locale 间 parity 门禁的测量盲区，杜绝「组件引用但 SSOT 缺失」导致的运行时原始 key（MISSING_MESSAGE）。
内容补齐工作流：`scripts/i18n-dump-remaining.mjs` 导出剩余壳 → `scripts/translation-patches/<locale>/batch-NN.json`（或 `scripts/i18n-de-bulk-translate.py` 批量机翻 + `auto-translated-overrides.json`）→ `scripts/i18n-patch-apply.mjs` / 直接写回 `locales/<locale>.json`；术语约束见 `scripts/i18n-glossary.json`（de Sie-Form / ko 敬语；`forbidden` 由 `verify-i18n.mjs` 强制执行）。
