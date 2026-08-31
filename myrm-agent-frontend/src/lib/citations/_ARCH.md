# citations/

## 架构概述

Inline 引用角标解析 SSOT：`MessageBox` 累积会话 sources 后交给 `MarkdownContent`，正文 cite 标记统一在此预处理为 `<citation>` 标签。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| ---- | ---- | ---- | ----- |
| `preprocessCitationMarkers.ts` | 核心 | 解析 `【N】`、`[N]`、`[citation:Title](url)` → `<citation>`；按 `source.index` 匹配 | ✅ |
| `maskCodeRegions.ts` | 核心 | fenced/inline code 掩码，避免代码字面量被误识别为 cite | ✅ |
| `__tests__/preprocessCitationMarkers.test.ts` | 测试 | 三格式 + code mask 单测 | — |

## 依赖

- `@/store/chat/types`（`Source`、`resolveSourceClickUrl`）
- 消费方：`components/features/message-box/MarkdownContent.tsx`
