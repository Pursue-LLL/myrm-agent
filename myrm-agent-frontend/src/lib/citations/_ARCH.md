# citations/

## 架构概述

Inline 引用角标解析 SSOT：助手气泡（`AssistantMessage`）经 `buildCitationSources` 取得本条消息的 cite 来源（本条自己的 sources 优先，缺的编号取最近的更早消息）后交给 `MarkdownContent`，正文 cite 标记统一在此预处理为 `<citation>` 标签；角标只按编号认来源，没有对应编号的标记保持原文。同时是来源取名 SSOT：一个来源属于哪一类、名字放在哪个字段只在 `sourceName.ts` 说一次，来源卡片、引用悬浮卡、复制与各种导出叫同一个名字。

## 文件清单

| 文件                                          | 地位 | 职责                                                                                                                                                                                                                                                                                                                                            | I/O/P |
| --------------------------------------------- | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `preprocessCitationMarkers.ts`                | 核心 | 解析单引用、复合引用（`[1, 2]`、`【1, 2】`、`【1-3】`）、变体括号与平衡小括号 URL `[citation:Title](url)` → `<citation>` 标签；泛称标题多语言智能域名回退；清洗大模型私有控制 token（`\ue200cite`）；按 `source.index` 匹配，没有对应编号的标记保持原文，不按位置猜                                                                             | ✅    |
| `buildCitationSources.ts`                     | 核心 | `buildCitationSources(earlier, own)`：一条消息的 cite 来源 = 本条自己的 sources（经 `mergeMessageSources` 规整，编号互不相同）+ 更早消息里本条没有的编号（从最近的消息往前取，一个编号只取一次，编号不可用的跳过），按编号排序                                                                                                                  | ✅    |
| `auditCitationMarkers.ts`                     | 核心 | 零 LLM 校验 fullwidth【N】与 source 数量；`resolveSourceCountForAudit` 与 harness 对齐                                                                                                                                                                                                                                                          | ✅    |
| `maskCodeRegions.ts`                          | 核心 | fenced/inline code 掩码，避免代码字面量被误识别为 cite                                                                                                                                                                                                                                                                                          | ✅    |
| `sourceName.ts`                               | 核心 | `sourceKind` / `sourceName`：来源属于哪一类（知识库 / 会话 / MCP / 网页，知识库名或技能名先于 `type` 定类），各类把名字放在哪个字段（知识库取文件名、有章节时附上经 `sectionLabel` 译成界面语言的章节，没有文件名取知识库名；MCP 取技能名；会话与网页取标题）；没有名字返回 `undefined`，占位词由调用方按自己说话的场合给；新增一类来源只改这里 | ✅    |
| `__tests__/auditCitationMarkers.test.ts`      | 测试 | marker audit + source count 单测                                                                                                                                                                                                                                                                                                                | —     |
| `__tests__/preprocessCitationMarkers.test.ts` | 测试 | 单引用、复合引用、范围展开、变体括号、平衡小括号 URL、按编号而非位置认来源、泛称域名回退、私有控制 token 清洗与 code mask 单测                                                                                                                                                                                                                  | —     |
| `__tests__/sourceName.test.ts`                | 测试 | 服务端各类来源的真实形状取名、章节译名与缺省、没有名字、空字段按未命名、没有 `type` 时按携带的名字归类                                                                                                                                                                                                                                          | —     |
| `__tests__/buildCitationSources.test.ts`      | 测试 | 本条优先、最近的更早消息优先、不可用编号跳过、字符串编号、无编号来源补号与不改入参单测                                                                                                                                                                                                                                                          | —     |

## 依赖

- `@/store/chat/types`（`Source`、`resolveSourceClickUrl`）
- `@/store/chat/messageStream/streamHelpers`（`mergeMessageSources`）
- 消费方：`components/features/message-box/assistant-message/AssistantMessage.tsx`（`buildCitationSources`）、`components/features/message-box/MarkdownContent.tsx`（`preprocessCitationMarkers`）；`sourceName` 的消费方：`components/features/message-actions/SourceItem.tsx`、`components/features/message-box/markdownComponents.tsx`、`lib/utils/chat-export/chatExportMessageText.ts`、`lib/utils/chat-export/chatExportHtml.ts`
