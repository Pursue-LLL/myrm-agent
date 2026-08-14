# settings/sections/knowledge/wiki/

## Overview

Settings Wiki 词条管理 UI：目录树 CRUD、拖拽排序、Markdown 预览；**四标签窄写编辑**（Compiled Truth / Timeline / Metadata / Advanced）；SaveToWiki 复用文件夹选择树。

## File Index

| File                            | Role | Description                                               | I/O/P |
| ------------------------------- | ---- | --------------------------------------------------------- | ----- |
| useWikiConceptsList.ts          | Core | 词条树状态 + **apply 窄写** 保存编排；`if_match` 来自 `content_hash`；save/delete 后 `onVaultMutated` 刷新 Overview stats | ✅    |
| WikiConceptTree.tsx             | UI   | react-arborist 管理树；`ingest_status` amber 点标示关联源过期 | ✅    |
| WikiConceptDetailPanel.tsx      | UI   | 预览 + **四标签编辑** + 结构化 claims 展示（`lib/wiki/claimStatusDisplay` badge）；来源对话消息级/会话级跳转 | ✅    |
| WikiRawSourceTree.tsx           | UI   | Overview raw 目录树；三色 ingest 点；Settings 侧 forget raw（reason dialog） | ✅    |
| WikiFolderSelectTree.tsx        | UI   | 仅文件夹的选择树（Create/SaveToWiki 复用）                | ✅    |
| ../WikiHealthIssuesSection.tsx  | UI   | Overview 健康报告：lint issues + duplicate/synthesis 快捷入口 | ✅    |
| WikiImportConflictDialog.tsx    | UI   | Batch import raw 冲突：保留现有 vs 填写 reason 后 supersede | ✅    |
| WikiImportSecurityDialog.tsx    | UI   | Batch import 安全拦截/脱敏摘要（`security_blocked_paths` / `security_redacted_paths`） | ✅    |
| wikiTreeUtils.ts                | Util | 树过滤、子项计数、API 错误解析、`extractSourceChatIdFromFrontmatter`、`extractSourceMessageIdFromFrontmatter`、父目录推断 | ✅    |
| wikiSectionUtils.ts             | Util | Metadata comma-split + health issue navigation + maintain→healthReport mapper | ✅    |
| **tests**/wikiSectionUtils.test.ts | Test | navigation + maintain overlay 单测                         | ✅    |
| **tests**/wikiTreeUtils.test.ts | Test | 树工具 + 溯源 frontmatter 解析（source_chat/source_message）单测 | ✅    |
| **tests**/WikiConceptDetailPanel.sourceJump.test.tsx | Test | 概念详情来源对话跳转（消息级/会话级/无来源） | ✅    |

## Dependencies

- `services/wikiService.ts` (POS: Wiki REST 客户端，含 `applyWiki` + `Concept.content_hash` + `editor_sections`)
- `hooks/ui/useMediaQuery.ts` (POS: 响应式断点检测)
- `hooks/settings/useSettingsSubTabUrl.ts` (POS: Settings 子 Tab URL 同步守卫)
- `components/features/message-box/MarkdownContent.tsx` (POS: Markdown 渲染)
- `lib/wiki/claimStatusDisplay.ts` (POS: Wiki claim 状态展示纯函数)

## API Surface

- Settings → Wiki → 词条管理：`WikiConceptsList`（父级编排于 `../WikiConceptsList.tsx`）
- Chat→Wiki 写入三入口（均传 `useChatStore.agentConfig.agentId`）：
  - `message-actions/SaveToWikiButton.tsx` → `POST /wiki/compound` 待审核沉淀（禁止 chat `create_note` 直发）
  - `artifacts/ArtifactCard.tsx` → artifact ingest
  - `research/ResearchOutputPanel.tsx` → artifact ingest

## Safety UX

- 删除 folder：展示 path + 子项 count（`deleteFolderConfirmDetail`）
- 新建 folder：Dialog 内显式父目录树选择
- SaveToWiki：提交 Pending 待审核；同名 pending 草稿由 harness 覆盖；chat caller 禁止直发 publish
- Settings 保存：并发冲突 `pageConflict` toast；Timeline duplicate `timelineDuplicateSkipped`
- Settings Advanced：整页 replace 前内联警告文案（settings caller only）
- Batch import：首次默认 skip 冲突；`conflict_paths` 非空时弹出 `WikiImportConflictDialog` 可 supersede 重试
- Batch import 安全：`security_blocked_paths` / `security_redacted_paths` 非空时弹出 `WikiImportSecurityDialog`
- Raw forget：Overview raw 树删除 → reason → `DELETE /wiki/raw/{path}`；移动端删除按钮常显
- Maintain：若移除 blocked raw，toast 展示 `raw_security_removed` 与路径列表
- Maintain（Full）：POST 响应 issues overlay 健康列表；GET 合并 vault 快照 drift（刷新仍可见）
