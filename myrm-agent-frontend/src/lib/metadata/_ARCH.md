# lib/metadata/ 模块架构

## 架构概述

Next.js `generateMetadata` 等构建期元数据所需的文案快照。与 `src/i18n/`（运行时 locale 路由）分离：此处仅在 **build time** 读取 `#locales` JSON，避免在 metadata 层引入 React / next-intl 客户端依赖。

## 文件清单

| 文件 | 职责 |
|------|------|
| `static-metadata.ts` | `getBuildTimeMetadataMessages()` — 从 `locales/namespaces/zh/metadata.json` 读取构建期 metadata |

## 依赖

- `locales/namespaces/zh/metadata.json` — 构建期 metadata 文案（由 `i18n:split` 从 `locales/zh.json` 生成）

## 约束

- 仅放构建期 metadata 辅助；运行时 i18n 见 `src/i18n/` 与 `lib/i18n/`
- 禁止硬编码用户可见 metadata 文案
