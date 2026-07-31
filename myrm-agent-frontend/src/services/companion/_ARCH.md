# services/companion/

## 架构概述

Companion 业务辅助模块（非 harness）。提供 Petdex 精灵图本地 URL 解析、install API 与 `/pet` slash 执行，供 store、Gallery、PetOverlay 与命令面板使用。

## 文件清单

| 文件 | 地位 | 职责 |
| --- | --- | --- |
| `petSpritesheet.ts` | 核心 | `petSlug` → `GET /companion/pets/{slug}/spritesheet` URL 解析 |
| `petInstall.ts` | 辅助 | `listInstalledCompanionPets()` → GET `/companion/pets`；`installCompanionPet(slug)` → POST `/companion/pets/install`；`uninstallCompanionPet(slug)` → DELETE `/companion/pets/{slug}` |
| `petSlashCommand.ts` | 辅助 | `parsePetSlashArgs` / `executePetSlashCommand` — `/pet` slash 执行 |

## 模块依赖

- `@/lib/api` — API 基址与请求
- `@/store/useCompanionStore` — 精灵配置与 palette 开关
- `@/store/useFeatureGateStore` — `companion_mode` 门控
- `@/components/features/companion/sprite/PetOverlay.tsx` — 消费 `resolveCompanionSpritesheetUrl`
- `@/components/features/companion/PetGallery.tsx` — 消费 `listInstalledCompanionPets` / `installCompanionPet`
- `@/components/features/companion/PetPalette.tsx` — 由 slash 打开
- `@/store/builtinActions.ts` — 注册 `builtin:pet`
