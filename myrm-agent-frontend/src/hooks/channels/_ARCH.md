# channels/

## 架构概述

渠道多实例管理 React hooks：连接 UI 与 `@/services/channels`，供各渠道配置区（飞书多应用区、微信配置卡）复用实例 CRUD。

## 文件清单

| 文件                          | 职责                                                                                                                                                                   | I/O/P |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `useChannelInstances.ts`      | 渠道多实例通用 CRUD hook：list / add / remove / rename + i18n toast + `onChange` 回调；增删改后同步实例列表。飞书多应用区与微信配置卡复用（消除重复实例管理逻辑）。    | ✅    |
| `useChannelInstancesStore.ts` | 共享实例状态（zustand，keyed by channelType）。桌面端设置页会同时挂载同一配置卡两份（右侧面板 + 响应式列表内详情），store 保证一处增删改在两处同步，避免残留陈旧卡片。 | ✅    |

## 依赖

- `@/services/channels` — REST 客户端（create / delete / list / rename 实例）
- `zustand` — 跨配置卡实例的共享实例列表
- `next-intl` / `sonner` — i18n 文案与 toast 提示

## 约束

- 遵循根 [_ARCH.md](../_ARCH.md) 约束：不写 UI JSX、不做桶导出。
