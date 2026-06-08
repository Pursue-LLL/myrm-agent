# shared/config/ 模块架构

## 架构概述

前后端共享的静态 JSON 配置。

## 文件清单

| 文件 | 职责 | 消费者 |
|------|------|--------|
| `provider_legacy_remap.json` | 遗留 providerId → canonical storage id | `providers.py` · `providerIdentityMigration.ts` |
