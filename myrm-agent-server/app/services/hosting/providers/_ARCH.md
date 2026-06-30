# services/hosting/providers/

## 架构概述

多托管平台 Provider 实现层。每个文件实现 `HostingProvider` 协议，负责单一平台的 preflight、publish 与状态轮询。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `vercel.py` | Provider | Vercel 静态部署 |
| `cloudflare_pages.py` | Provider | Cloudflare Pages 部署 |
| `netlify.py` | Provider | Netlify 部署 |
| `http_webhook.py` | Provider | 通用 HTTP Webhook 回调（含 SSRF 防护） |

## 依赖关系

- `app.services.hosting.protocols::HostingProvider`
- `app.services.hosting.ssrf_guard`（webhook 出站校验）
