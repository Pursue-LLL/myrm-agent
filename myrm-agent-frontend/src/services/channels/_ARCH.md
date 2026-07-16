# channels/ 模块架构

## 架构概述

`@/services/channels` 分片实现：核心工厂、渠道管理 API、各 Provider 凭证、异步登录协议。`channels.ts` 为 facade re-export。

## 文件清单

| 文件 | 职责 |
|------|------|
| `core.ts` | CP 请求、`createChannelCredentialService` 工厂、`ChannelTestResult` |
| `manage.ts` | 类型、状态/实例、配对、策略、群组、路由绑定 |
| `providersMessaging.ts` | WhatsApp / IM 类 Provider 凭证与测试 |
| `providersEnterprise.ts` | 企业/开发类 Provider 凭证与测试 |
| `login.ts` | 异步登录 start / SSE / cancel |

## 依赖

- `@/lib/api`
- `@/types/channels`（login）
- 父模块 [services/_ARCH.md](../_ARCH.md)
