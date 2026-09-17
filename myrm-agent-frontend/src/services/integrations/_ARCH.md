# services/integrations/

## 架构概述

个人 SaaS OAuth 集成凭证的只读 API 客户端，供 Settings 数据流披露与集成管理复用。

## 文件清单

| 文件                  | 地位 | 职责                                                       | I/O/P |
| --------------------- | ---- | ---------------------------------------------------------- | ----- |
| `oauthCredentials.ts` | 核心 | `listOAuthCredentials()`：拉取已连接集成的只读凭证元数据   | ✅    |

## 依赖

- `@/lib/api` — `apiRequest`（前端 API 接入层）
- 父模块 [`../_ARCH.md`](../_ARCH.md)
