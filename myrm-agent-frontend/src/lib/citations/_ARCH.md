# citations/

## 架构概述

Inline 引用角标解析 SSOT：`MessageBox` 累积会话 sources 后交给 `MarkdownContent`，正文 cite 标记统一在此预处理为 `<citation>` 标签。

## 文件清单

| 文件                                          | 地位 | 职责                                                                                                                                                                                                                        | I/O/P |
| --------------------------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `preprocessCitationMarkers.ts`                | 核心 | 解析单引用、复合引用（`[1, 2]`、`【1, 2】`、`【1-3】`）、变体括号与平衡小括号 URL `[citation:Title](url)` → `<citation>` 标签；泛称标题多语言智能域名回退；清洗大模型私有控制 token（`\ue200cite`）；按 `source.index` 匹配 | ✅    |
| `auditCitationMarkers.ts`                     | 核心 | 零 LLM 校验 fullwidth【N】与 source 数量；`resolveSourceCountForAudit` 与 harness 对齐                                                                                                                                      | ✅    |
| `maskCodeRegions.ts`                          | 核心 | fenced/inline code 掩码，避免代码字面量被误识别为 cite                                                                                                                                                                      | ✅    |
| `__tests__/auditCitationMarkers.test.ts`      | 测试 | marker audit + source count 单测                                                                                                                                                                                            | —     |
| `__tests__/preprocessCitationMarkers.test.ts` | 测试 | 单引用、复合引用、范围展开、变体括号、平衡小括号 URL、泛称域名回退、私有控制 token 清洗与 code mask 单测                                                                                                                    | —     |

## 依赖

- `@/store/chat/types`（`Source`、`resolveSourceClickUrl`）
- 消费方：`components/features/message-box/MarkdownContent.tsx`
