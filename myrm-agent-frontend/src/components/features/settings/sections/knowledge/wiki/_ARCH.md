# settings/sections/knowledge/wiki/

## Overview

Settings Wiki 词条管理 UI：目录树 CRUD、拖拽排序、Markdown 预览；**四标签窄写编辑**（Compiled Truth / Timeline / Metadata / Advanced）；**分屏实时预览编辑器**（Monaco 源码 + MarkdownContent 渲染）；SaveToWiki 复用文件夹选择树。

## File Index

| File                                                 | Role | Description                                                                                                                                                                                                       | I/O/P |
| ---------------------------------------------------- | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| useWikiConceptsList.ts                               | Core | 词条树状态 + **apply 窄写** 保存编排；`if_match` 来自 `content_hash`；save/delete 后 `onVaultMutated` 刷新 Overview stats                                                                                         | ✅    |
| WikiConceptTree.tsx                                  | UI   | react-arborist 管理树；`ingest_status` amber 点标示关联源过期                                                                                                                                                     | ✅    |
| WikiConceptDetailPanel.tsx                           | UI   | 预览 + 视频笔记内嵌播放（`VideoKnowledgePlayer`）+ **四标签编辑**（truth/advanced 用分屏实时预览编辑器）+ 结构化 claims 展示（`lib/wiki/claimStatusDisplay` badge）；来源对话消息级/会话级跳转 | ✅    |
| WikiMarkdownEditor.tsx                               | UI   | **分屏实时预览编辑器**：Monaco 源码（懒加载）+ MarkdownContent 实时渲染；`useDeferredValue` 防抖、受控写回保光标、Cmd/Ctrl+S、移动端编辑/预览 Tab；`onMount` 暴露 `window.__wikiMarkdownEditor` 供 E2E 编程式输入 | ✅    |
| WikiRawSourceTree.tsx                                | UI   | Overview raw 目录树；三色 ingest 点；Settings 侧 forget raw（reason dialog）                                                                                                                                      | ✅    |
| WikiFolderSelectTree.tsx                             | UI   | 仅文件夹的选择树（Create/SaveToWiki 复用）                                                                                                                                                                        | ✅    |
| ../WikiHealthIssuesSection.tsx                       | UI   | Overview 健康报告：lint issues + duplicate/synthesis 快捷入口                                                                                                                                                     | ✅    |
| WikiImportConflictDialog.tsx                         | UI   | Batch import raw 冲突：保留现有 vs 填写 reason 后 supersede                                                                                                                                                       | ✅    |
| WikiImportSecurityDialog.tsx                         | UI   | Batch import 安全拦截/脱敏摘要（`security_blocked_paths` / `security_redacted_paths`）                                                                                                                            | ✅    |
| WikiUrlImportDialog.tsx                              | UI   | 网页链接批量导入 Dialog（多行 URL 解析、去重校验、上限 50、SSRF 安全防御、入队提示）                                                                                                                              | ✅    |
| WikiVideoImportDialog.tsx                            | UI   | 在线音视频导入 Dialog（Bilibili/YouTube URL 校验、目标目录与滑动窗口配置、入库提示）                                                                                                                                 | ✅    |
| VideoKnowledgePlayer.tsx                             | UI   | 视频知识播放器（Bilibili/YouTube/原生视频自适应内嵌、秒级时间戳 seek、章节列表导航、Frontmatter 视频元数据与章节解析）                                                                                              | ✅    |
| wikiTreeUtils.ts                                     | Util | 树过滤、子项计数、API 错误解析、`extractSourceChatIdFromFrontmatter`、`extractSourceMessageIdFromFrontmatter`、父目录推断                                                                                         | ✅    |
| wikiSectionUtils.ts                                  | Util | Metadata comma-split + health issue navigation + maintain→healthReport mapper                                                                                                                                     | ✅    |
| **tests**/wikiSectionUtils.test.ts                   | Test | navigation + maintain overlay 单测                                                                                                                                                                                | ✅    |
| **tests**/wikiTreeUtils.test.ts                      | Test | 树工具 + 溯源 frontmatter 解析（source_chat/source_message）单测                                                                                                                                                  | ✅    |
| **tests**/WikiConceptDetailPanel.sourceJump.test.tsx | Test | 概念详情来源对话跳转（消息级/会话级/无来源）                                                                                                                                                                      | ✅    |
| **tests**/VideoKnowledgePlayer.test.ts               | Test | 视频播放器嵌入、时间戳解析、Frontmatter 元数据抽取与 URL 校验单测                                                                                                                                                 | ✅    |

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
- Settings 编辑：切换词条/取消编辑时若有未保存修改，弹「放弃未保存更改」确认（`discardUnsaved*`），避免静默丢稿
- Settings 编辑：切换词条/取消编辑时若有未保存修改，弹「放弃未保存更改」确认（`discardUnsaved*`），避免静默丢稿
- Settings Advanced：整页 replace 前内联警告文案（settings caller only）
- Batch import：首次默认 skip 冲突；`conflict_paths` 非空时弹出 `WikiImportConflictDialog` 可 supersede 重试
- Batch import 安全：`security_blocked_paths` / `security_redacted_paths` 非空时弹出 `WikiImportSecurityDialog`
- Raw forget：Overview raw 树删除 → reason → `DELETE /wiki/raw/{path}`；移动端删除按钮常显
- Maintain：若移除 blocked raw，toast 展示 `raw_security_removed` 与路径列表
- Maintain（Full）：POST 响应 issues overlay 健康列表；GET 合并 vault 快照 drift（刷新仍可见）
