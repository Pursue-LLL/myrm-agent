# lib/i18n/ 模块架构

## 架构概述

非 React 运行时的 i18n 辅助层（SSE 流处理器、OS 通知等无法使用 `useTranslations` 的场景）。**与 `src/i18n/`（next-intl 路由/cookie）职责不同**，勿混用。

| 路径 | 职责 |
|------|------|
| `src/i18n/` | App Router locale 解析、cookie、`next-intl` 配置 |
| `lib/i18n/`（本目录） | 纯函数：从 `#locales` JSON 解析通知文案等 |

## 文件清单

| 文件 | 职责 |
|------|------|
| `streamNotificationCopy.ts` | `resolveStreamLocale`、`getClarificationNotificationTitle`（`notifications.clarificationNeeded` SSOT） |

## 依赖

- `#locales/*.json` — 五语系文案 SSOT
- 消费者：`src/store/chat/messageStream/handlers/*`（非组件层）

## 约束

- 新非 React i18n 辅助放本目录；路由级 i18n 仍放 `src/i18n/`
- 禁止硬编码用户可见文案
