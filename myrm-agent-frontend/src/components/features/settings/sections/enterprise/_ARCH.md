# settings/sections/enterprise/ 模块架构

## 架构概述

SaaS / sandbox 部署下的 Enterprise Org 管理 Section（`SettingsMenu` 中 `group: system`、`sandboxOnly: true`）。单机 OSS 构建不展示此 Tab。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `EnterpriseOrgSection.tsx` | 核心 | 组织信息、成员 CRUD、离职交接、Volume 转移、Handoff 日志 | ✅ |

## 依赖

- `@/services/enterprise-org` — Org API 客户端
- [`../SettingsSection.tsx`](../SettingsSection.tsx) — Section 容器
- 父模块 [`../_ARCH.md`](../_ARCH.md)
