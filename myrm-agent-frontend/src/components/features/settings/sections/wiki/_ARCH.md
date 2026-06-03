# settings/sections/wiki/

## Overview

Settings Wiki 词条管理 UI：目录树 CRUD、拖拽排序、Markdown 预览编辑；SaveToWiki 对话框复用文件夹选择树。

## File Index

| File                            | Role | Description                                               | I/O/P |
| ------------------------------- | ---- | --------------------------------------------------------- | ----- |
| useWikiConceptsList.ts          | Core | 词条树状态与 API 编排（加载/移动/重命名/删除/父目录创建） | ✅    |
| WikiConceptTree.tsx             | UI   | react-arborist 管理树（移动端常显操作按钮）               | ✅    |
| WikiConceptDetailPanel.tsx      | UI   | 词条 Markdown 预览与编辑面板                              | ✅    |
| WikiFolderSelectTree.tsx        | UI   | 仅文件夹的选择树（Create/SaveToWiki 复用）                | ✅    |
| wikiTreeUtils.ts                | Util | 树过滤、子项计数、API 错误解析、父目录推断                | ✅    |
| **tests**/wikiTreeUtils.test.ts | Test | 树工具函数单测                                            | ✅    |

## Dependencies

- `services/wikiService.ts` (POS: Wiki REST 客户端，对接 `/wiki/tree/*`)
- `hooks/useMediaQuery.ts` (POS: 响应式断点检测)
- `hooks/useSettingsSubTabUrl.ts` (POS: Settings 子 Tab URL 同步守卫)
- `components/features/message-box/MarkdownContent.tsx` (POS: Markdown 渲染)

## API Surface

- Settings → Wiki → 词条管理：`WikiConceptsList`（父级编排于 `../WikiConceptsList.tsx`）
- 聊天消息栏：`message-actions/SaveToWikiButton.tsx` → 覆盖确认 + `WikiFolderSelectTree`

## Safety UX

- 删除 folder：展示 path + 子项 count（`deleteFolderConfirmDetail`）
- 新建 folder：Dialog 内显式父目录树选择
- SaveToWiki：同名路径覆盖前 AlertDialog 确认；写入 YAML frontmatter（source_chat/source_message/saved_at）
