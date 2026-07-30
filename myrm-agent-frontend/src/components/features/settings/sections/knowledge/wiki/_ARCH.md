# settings/sections/knowledge/wiki/

## Overview

Settings Wiki 词条管理 UI：目录树 CRUD、拖拽排序、Markdown 预览；**四标签窄写编辑**（Compiled Truth / Timeline / Metadata / Advanced）；SaveToWiki 复用文件夹选择树。

## File Index

| File                            | Role | Description                                               | I/O/P |
| ------------------------------- | ---- | --------------------------------------------------------- | ----- |
| useWikiConceptsList.ts          | Core | 词条树状态 + **apply 窄写** 保存编排；`if_match` 来自 `content_hash`；save/delete 后 `onVaultMutated` 刷新 Overview stats | ✅    |
| WikiConceptTree.tsx             | UI   | react-arborist 管理树；`ingest_status` amber 点标示关联源过期 | ✅    |
| WikiConceptDetailPanel.tsx      | UI   | 预览 + **四标签编辑** + 结构化 claims 展示（`lib/wiki/claimStatusDisplay` badge） | ✅    |
| WikiRawSourceTree.tsx           | UI   | Overview raw 目录树；三色 ingest 点；Settings 侧 forget raw（reason dialog） | ✅    |
| WikiFolderSelectTree.tsx        | UI   | 仅文件夹的选择树（Create/SaveToWiki 复用）                | ✅    |
| WikiImportConflictDialog.tsx    | UI   | Batch import raw 冲突：保留现有 vs 填写 reason 后 supersede | ✅    |
| WikiImportSecurityDialog.tsx    | UI   | Batch import 安全拦截/脱敏摘要（`security_blocked_paths` / `security_redacted_paths`） | ✅    |
| wikiTreeUtils.ts                | Util | 树过滤、子项计数、API 错误解析（含 `getWikiErrorCode`）、父目录推断                | ✅    |
| wikiSectionUtils.ts             | Util | Metadata editor comma-split helper (`splitTagsInput`)     | ✅    |
| **tests**/wikiTreeUtils.test.ts | Test | 树工具函数单测                                            | ✅    |

## Dependencies

- `services/wikiService.ts` (POS: Wiki REST 客户端，含 `applyWiki` + `Concept.content_hash` + `editor_sections`)
- `hooks/ui/useMediaQuery.ts` (POS: 响应式断点检测)
- `hooks/settings/useSettingsSubTabUrl.ts` (POS: Settings 子 Tab URL 同步守卫)
- `components/features/message-box/MarkdownContent.tsx` (POS: Markdown 渲染)
- `lib/wiki/claimStatusDisplay.ts` (POS: Wiki claim 状态展示纯函数)

## API Surface

- Settings → Wiki → 词条管理：`WikiConceptsList`（父级编排于 `../WikiConceptsList.tsx`）
- Chat→Wiki 写入三入口（均传 `useChatStore.agentConfig.agentId`）：
  - `message-actions/SaveToWikiButton.tsx` → `create_note` / 覆盖时 `patch_compiled_truth` + `append_timeline`
  - `artifacts/ArtifactCard.tsx` → artifact ingest
  - `research/ResearchOutputPanel.tsx` → artifact ingest

## Safety UX

- 删除 folder：展示 path + 子项 count（`deleteFolderConfirmDetail`）
- 新建 folder：Dialog 内显式父目录树选择
- SaveToWiki：同名路径覆盖前 AlertDialog；窄写更新 Compiled Truth + Timeline 追加；canonical 冲突 toast
- Settings 保存：并发冲突 `pageConflict` toast；Timeline duplicate `timelineDuplicateSkipped`
- Settings Advanced：整页 replace 前内联警告文案（settings caller only）
- Batch import：首次默认 skip 冲突；`conflict_paths` 非空时弹出 `WikiImportConflictDialog` 可 supersede 重试
- Batch import 安全：`security_blocked_paths` / `security_redacted_paths` 非空时弹出 `WikiImportSecurityDialog`
- Raw forget：Overview raw 树删除 → reason → `DELETE /wiki/raw/{path}`；移动端删除按钮常显
- Maintain：若移除 blocked raw，toast 展示 `raw_security_removed` 与路径列表
