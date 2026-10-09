# redaction/

## 架构概述

导出前的脱敏复核，技能导出与专家导出共用：预览给出每个文件的发现（原文 → 占位），作者逐条决定「脱敏（默认）」或「原样保留」；导出时把决定连同预览摘要（`review_digest`）一并回传，后端据此确认决定所依据的内容没有变化。

决定语义：`ignored[path]` 为作者选择**保留原文**的发现索引，空表示全部脱敏。「导出原文」必须对每条发现显式声明保留（`keepEveryFinding`）；携带保留决定却没有预览摘要的请求会被后端拒绝（`redaction_review_required`）。

## 文件清单

| 文件                                      | 地位 | 职责                                                                                                                                                                                         | I/O/P |
| ----------------------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `useRedactionDecisions.ts`                | 核心 | 复核状态 hook（`ignored` / `toggle` / `toggleAll` / `reset`）与纯函数 `keepEveryFinding`、`hasKeptFindings`；预览重载时 `reset`                                                              | ✅    |
| `RedactionReview.tsx`                     | 核心 | 逐文件 diff 复核列表：勾选 = 脱敏，取消勾选 = 保留原文；每条发现按 `kinds` 稳定码显示本地化类型（`common.redactionReview.kinds.*`，未知码回落到 `unknown`）；`disabled` 在导出进行中锁定决定 | ✅    |
| `__tests__/useRedactionDecisions.test.ts` | 测试 | 决定语义：逐条切换、整文件切换（部分保留时重新全部脱敏）、重置、`keepEveryFinding`                                                                                                           | ✅    |
| `__tests__/RedactionReview.test.tsx`      | 测试 | 渲染原文与占位、本地化类型（多类型拼接、未知码回落）、保留项不显示占位行、切换回调、勾选状态、禁用态                                                                                         | ✅    |

## 依赖

- `@/services/skill`（`RedactionResponse` 形状）、`@/components/primitives/*`
- 消费方：`features/skills/SkillExportDialog`、`features/plugins/ExpertExportDialog`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
