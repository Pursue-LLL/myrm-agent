# store/skill/ 模块架构

## 架构概述

技能选择与进化草稿状态。列表/详情 API 在 `@/services/skill*`；进化审核 UI 状态在 `useSkillDraftStore`。

## 文件清单

| 文件 | 职责 |
|------|------|
| `useSkillStore.ts` | 技能列表、选中技能、安装状态 |
| `useSkillDraftStore.ts` | 进化/优化草稿与审核队列 |
| `types.ts` | 技能 store 专用类型 |
| `index.ts` | 再导出（子模块唯一允许的桶入口） |

## 依赖

- `@/services/skill.ts`、`skill-growth.ts` — REST
- `@/components/features/skills/*` — 消费方

## 约束

- 技能 API 类型以 `services/skill.ts` 为准，store 仅持 UI 投影
