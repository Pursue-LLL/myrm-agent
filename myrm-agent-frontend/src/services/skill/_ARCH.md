# skill/ 模块架构

## 架构概述

`@/services/skill` 分片实现：技能 CRUD 核心、进化、优化、迁移。`skill.ts`（根）为 facade re-export。

## 文件清单

| 文件 | 职责 |
|------|------|
| `core.ts` | `/skills/*` CRUD、生命周期、用户配置、扫描、本机路径；`approveSkillDraft` / `rejectSkillDraft` |
| `growth.ts` | `/skill-growth/*`：cases（含 `total`）、detail、stats、audit |
| `optimization.ts` | `/skill-optimization/*` 质量历史、版本列表/对比/回滚、Shadow A/B 启动；`/batch-optimization/tasks/{id}/cancel` 与 `rollback` |
| `migration.ts` | External assistant skill migration staging 与 review client |

## 依赖

- `@/lib/api`
- `@/store/skill/types`（core 复用 Skill DTO）
- `skill/core.ts`（growth 复用 `approveSkillDraft` / `rejectSkillDraft`）
- 父模块 [services/_ARCH.md](../_ARCH.md)
