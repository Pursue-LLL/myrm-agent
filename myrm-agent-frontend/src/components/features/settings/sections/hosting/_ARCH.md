# settings/sections/hosting 模块架构

---

## 架构概述

Settings 中 Hosting Targets 配置面板：Vercel / Cloudflare Pages / Netlify / HTTP Webhook 四类 target 的 CRUD、凭证保存、连接测试与默认 target 设置。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `HostingTargetsPanel.tsx` | 核心 | target 列表、表单、make-default、删除 |

---

## 依赖关系

- `@/services/hosting.ts` — targets CRUD、credentials、test、make-default
- Settings 路由 tab id：`hosting`（路径 `/settings/hosting`）
