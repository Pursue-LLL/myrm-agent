# services/companion/

## 架构概述

Companion Petdex 与 sprite 健康检查的前端 API 客户端与纯函数。上级文档：[../_ARCH.md](../_ARCH.md)。UI 编排见 [../../components/features/companion/_ARCH.md](../../components/features/companion/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `petInstall.ts` | 核心 | GET/POST/DELETE `/companion/pets`；`CompanionFeatureDisabledError` | ✅ |
| `petDoctor.ts` | 核心 | `GET /companion/doctor`；`openCompanionHealthCheck()` → store | ✅ |
| `petSpritesheet.ts` | 辅助 | 本地 Volume spritesheet URL | ✅ |
| `companionFormatLabelCore.ts` | 辅助 | 已安装 pet `format_tier` → gallery i18n key | ✅ |
| `companionDoctorCheckI18nCore.ts` | 辅助 | server doctor `check.id` → `doctor.serverChecks.*` i18n | ✅ |

## 依赖

- `@/lib/api` — HTTP
- `@/store/useCompanionStore` — health check 打开 Pet Palette（`petDoctor` 仅 `openCompanionHealthCheck`）
