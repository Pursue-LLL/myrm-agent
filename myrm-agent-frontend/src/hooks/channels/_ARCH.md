# channels/

## 架构概述

渠道多实例管理 React hooks：连接 UI 与 `@/services/channels`，供各渠道配置区（飞书多应用区、微信配置卡）复用实例 CRUD。

## 文件清单

| 文件 | 职责 | I/O/P |
|------|------|-------|
| `useChannelInstances.ts` | 渠道多实例通用 CRUD hook：list / add / remove / rename + i18n toast + `onChange` 回调；增删改后同步本地实例列表。飞书多应用区与微信配置卡复用（消除重复实例管理逻辑）。 | ✅ |

## 依赖

- `@/services/channels` — REST 客户端（create / delete / list / rename 实例）
- `next-intl` / `sonner` — i18n 文案与 toast 提示

## 约束

- 遵循根 [_ARCH.md](../_ARCH.md) 约束：不写 UI JSX、不做桶导出。
