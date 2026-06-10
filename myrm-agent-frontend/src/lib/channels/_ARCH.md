# lib/channels/

## 架构概述

渠道 Ingress 展示类型与前端单测。运行时判定以 Server `GET /system/ingress-requirement` 为 SSOT。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `connectivity.ts` | 辅助 | `ChannelIngressMode` 类型；单测用本地判定函数（生产路径走 server API） | ✅ |

## 依赖

- `@/services/channels` — 仅类型 `FeishuCredentials`、`TelegramCredentials`

## 消费方

- `ChannelIngressBadge.tsx` — 渠道卡徽章
- `useIngressRequirement.ts` — 调用 `/system/ingress-requirement`；驱动 System 与 ChannelsSection 徽章
