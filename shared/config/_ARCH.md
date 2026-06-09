# shared/config/ 模块架构

## 架构概述

前后端共享的静态 JSON 配置。

## Normalize Contract

Legacy storage id remap 在前后端使用**同一算法**（与 [`providers.py`](../../myrm-agent-server/app/services/agent/params/providers.py) · [`providerIdentityMigration.ts`](../../myrm-agent-frontend/src/store/config/providerIdentityMigration.ts) 一致）：

1. `trim()` 首尾空白
2. `-` → `_`
3. `lower()` 小写
4. 查 `provider_legacy_remap.json`；未命中则返回 trim 后的原 id（不改大小写）

## 文件清单

| 文件 | 职责 | 消费者 |
|------|------|--------|
| `provider_legacy_remap.json` | 遗留 providerId → canonical storage id | `providers.py` · `providerIdentityMigration.ts` · Docker `/shared` · PyInstaller bundle · vitest · pytest |
