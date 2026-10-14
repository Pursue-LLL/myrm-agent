# settings/sections/knowledge/wiki/

## Overview

Settings Wiki 词条管理 UI：目录树 CRUD、拖拽排序、Markdown 预览；**四标签窄写编辑**（Compiled Truth / Timeline / Metadata / Advanced）；**分屏实时预览编辑器**（Monaco 源码 + MarkdownContent 渲染）；SaveToWiki 复用文件夹选择树。

## File Index

| File                                                 | Role | Description                                                                                                                                                                                                                                                           | I/O/P |
| ---------------------------------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| useWikiConceptsList.ts                               | Core | 词条树状态 + **apply 窄写** 保存编排；`if_match` 来自 `content_hash`；save/delete 后 `onVaultMutated` 刷新 Overview stats；词条选择只认最后一次发起的请求（快速连点、切换 Agent 范围时较早的响应与失败提示一律丢弃）；保存、声明操作返回时详情已换成别的词条（`shownConceptNameRef`）则不再改写选中词条与编辑区，删除按详情当前展示的词条判断是否清空                                                                                                                                             | ✅    |
| useWikiConceptClaimActions.ts                        | Core | 词条 Claim 状态更新与证据修复操作 Handler；经 `shownConceptNameRef` 判断刷新结果是否仍属于当前详情，迟到的刷新不覆盖新选择                                                                                                                                                                                                                             | ✅    |
| useConceptHeadingFocus.ts                            | Core | 详情面板的小节锚点聚焦 Hook：多帧渐进重试（两段式精确优先防劫持）、平滑滚动与高亮、瞬态消费复位与生命周期清理；同词条内跳转立即定位，跨词条先切换词条再定位                                                                                                                                                                                                                | ✅    |
| useWikiTreeActions.ts                                | Core | 词条树节点拖拽移动、新建文件夹、重命名与弹窗处理 Handler                                                                                                                                                                                                              | ✅    |
| WikiConceptTree.tsx                                  | UI   | react-arborist 管理树；`ingest_status` amber 点标示关联源过期                                                                                                                                                                                                         | ✅    |
| WikiConceptDetailPanel.tsx                           | UI   | 预览 + 视频笔记内嵌播放（`VideoKnowledgePlayer`）+ 反向链接卡片点击后的小节锚点聚焦委托 `useConceptHeadingFocus` + 头部「链接与上下文」快捷按钮（滚动到链接面板；窄屏收成纯图标，不再隐藏；文案与无障碍名取自 `links.title`）+ **四标签编辑**（truth/advanced 用分屏实时预览编辑器）；来源对话消息级/会话级跳转                               | ✅    |
| WikiConceptClaimsSection.tsx                         | UI   | 词条结构化声明（Claims）列表、证据链凭证下钻及治愈/验证治理操作组件                                                                                                                                                                                                   | ✅    |
| WikiEditorToolbar.tsx                                | UI   | **Wiki Markdown 格式工具栏**：加粗/斜体/二级标题/代码块/引用/无序列表/待办任务/Wiki双链（`[[]]`）/表格模板；矢量图标；深浅主题自适应                                                                                                                                  | ✅    |
| WikiMarkdownEditor.tsx                               | UI   | **分屏实时预览编辑器**：Monaco 源码（懒加载）+ MarkdownContent 实时渲染；WikiEditorToolbar 挂载与原生 executeEdits 执行；Cmd/Ctrl+B/I/K 原生快捷键绑定与空选区智能占位高亮；onDidScrollChange 平滑滚动比例同步；unmount 内存释放清理；Cmd/Ctrl+S、移动端编辑/预览 Tab | ✅    |
| WikiRawSourceTree.tsx                                | UI   | Overview raw 目录树；三色 ingest 点；Settings 侧 forget raw（reason dialog）                                                                                                                                                                                          | ✅    |
| WikiFolderSelectTree.tsx                             | UI   | 仅文件夹的选择树（Create/SaveToWiki 复用）                                                                                                                                                                                                                            | ✅    |
| ../WikiHealthIssuesSection.tsx                       | UI   | Overview 健康报告：lint issues + duplicate/synthesis 快捷入口                                                                                                                                                                                                         | ✅    |
| WikiImportConflictDialog.tsx                         | UI   | Batch import raw 冲突：保留现有 vs 填写 reason 后 supersede                                                                                                                                                                                                           | ✅    |
| WikiImportSecurityDialog.tsx                         | UI   | Batch import 安全拦截/脱敏摘要（`security_blocked_paths` / `security_redacted_paths`）                                                                                                                                                                                | ✅    |
| WikiUrlImportDialog.tsx                              | UI   | 网页链接批量导入 Dialog（多行 URL 解析、去重校验、上限 50、SSRF 安全防御、入队提示）                                                                                                                                                                                  | ✅    |
| WikiVideoImportDialog.tsx                            | UI   | 在线音视频导入 Dialog（Bilibili/YouTube URL 校验、目标目录与滑动窗口配置、入库提示）                                                                                                                                                                                  | ✅    |
| VideoKnowledgePlayer.tsx                             | UI   | 视频知识播放器（Bilibili/YouTube/原生视频自适应内嵌、秒级时间戳 seek、章节列表导航、Frontmatter 视频元数据与章节解析）                                                                                                                                                | ✅    |
| WikiConceptLinksPanel.tsx                            | UI   | 词条双向链接与脉络导航面板：反向引用列表（含所在小节徽章与按小节穿透跳转）、前置引用列表（含缺失页状态）；外层持有标签页选择，内层按「Agent 范围 + 词条」为 key 挂载，切换词条即丢弃旧数据与在途请求；加载失败统一展示本地化文案；某个方向的链接被服务端按上限截断时，该方向的计数显示为「N+」，另一方向照常；全部文案取自 settings.wiki.concepts.links 六语言命名空间                                                                                                                   | ✅    |
| WikiGovernanceWorkbench.tsx                          | UI   | 知识生命周期治理工作台：四队列看板（待审核草稿/即将过期/知识盲区/已归档）、90 天老化延期、原子隔离归档、30s 内存撤销与一键复活                                                                                                                                        | ✅    |
| `WikiLayersLedgerPanel.tsx`                          | UI   | 五层知识资产全局态势看板（L1-L5）；支持层级卡片交互选中、微观条目下钻列表抽屉、单键审阅单回写入口，全响应式适配                                                                                                                                                       | ✅    |
| `WikiLayerItemPreviewModal.tsx`                      | UI   | 分层资产微观文档条目只读 Markdown 与凭据元数据在线预览弹窗                                                                                                                                                                                                            | ✅    |
| `WikiReviewSlipModal.tsx`                            | UI   | 交付物作者审阅单人机决策弹窗：展现高价值决策单选题、5 类单次瞬态数据负向硬拦截统计盾牌、卡片单选与安全回写                                                                                                                                                            | ✅    |
| wikiTreeUtils.ts                                     | Util | 树过滤、子项计数、API 错误解析、`extractSourceChatIdFromFrontmatter`、`extractSourceMessageIdFromFrontmatter`、父目录推断                                                                                                                                             | ✅    |
| wikiSectionUtils.ts                                  | Util | Metadata comma-split + health issue navigation + maintain→healthReport mapper                                                                                                                                                                                         | ✅    |
| **tests**/wikiSectionUtils.test.ts                   | Test | navigation + maintain overlay 单测                                                                                                                                                                                                                                    | ✅    |
| **tests**/wikiTreeUtils.test.ts                      | Test | 树工具 + 溯源 frontmatter 解析（source_chat/source_message）单测                                                                                                                                                                                                      | ✅    |
| **tests**/WikiConceptDetailPanel.sourceJump.test.tsx | Test | 概念详情来源对话跳转（消息级/会话级/无来源）、小节锚点聚焦，以及链接面板快捷按钮（本地化标签、任何断点不隐藏、点击滚动到链接面板）                                                                                                                                                                                                                          | ✅    |
| **tests**/VideoKnowledgePlayer.test.ts               | Test | 视频播放器嵌入、时间戳解析、Frontmatter 元数据抽取与 URL 校验单测                                                                                                                                                                                                     | ✅    |
| **tests**/WikiEditorToolbar.test.tsx                 | Test | WikiEditorToolbar 按钮渲染、格式操作分发与 disabled 状态保护单测                                                                                                                                                                                                      | ✅    |
| **tests**/WikiConceptLinksPanel.test.tsx             | Test | WikiConceptLinksPanel 在真实 en/zh 文案下的双向引用渲染、上下文片段、Tab 切换、缺失页禁用、本地化错误兜底与重试、切换词条时不残留旧数据且保留标签页、迟到响应丢弃、被截断方向显示「N+」单测                                                                                                                                                                                                     | ✅    |
| **tests**/useWikiConceptsList.selection.test.ts      | Test | useWikiConceptsList 词条选择只认最后一次发起请求的单测：乱序响应、被取代请求的失败静默、最新请求失败提示、切换 Agent 范围丢弃在途选择                                                                                                                                                                                                                        | ✅    |

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
- Raw forget：Overview raw 树删除 → reason → `DELETE /wiki/raw/{path}`；删除按钮用 `REVEAL_ON_HOVER`（触屏常显，桌面悬停或键盘聚焦显示）
- Maintain：若移除 blocked raw，toast 展示 `raw_security_removed` 与路径列表
- Maintain（Full）：POST 响应 issues overlay 健康列表；GET 合并 vault 快照 drift（刷新仍可见）
