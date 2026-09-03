# artifacts/ 模块架构

---

## 架构概述

聊天流工件展示：Globe 多 target 发布、preflight 门禁、只读分享短链、知识库写入、对话附件插入。视觉型工件（HTML/SVG/Mermaid）默认在消息流内 inline 展开渲染（超过 `LARGE_FILE_THRESHOLD` 的大文件自动降级为全屏引导 CTA），其余类型保持卡片模式。卡片与全屏预览双入口一致。

---

## 文件清单

| 文件                                       | 地位 | 职责                                                                                                                                                                                                    |
| ------------------------------------------ | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ArtifactPortal.tsx`                       | 核心 | Artifact 预览入口容器；支持 overlay/side-by-side 双布局模式；协调加载、手势、快捷键与 Diff 截断 UX                                                                                                      |
| `DeliverablesBoard.tsx`                    | 核心 | 交付物全景看板：支持品类筛选（文章/图文/脚本/数据表/视觉/核查表）、关键词搜索、高保真卡片与一键整包流式 ZIP 打包                                                                                     |
| `FactCheckSheetViewer.tsx`                 | 核心 | 事实核查表专属可视化核查矩阵：红黄绿冲突对比、置信度审计、多源主张对照矩阵与原文锚点溯源                                                                                                               |
| `DeliverableBundleCard.tsx`                | 核心 | 会话消息流成套交付物卡片：展示成品数量徽章、品类统计与一键看板/打包导出                                                                                                                                |
| `deliverableTypes.ts`                      | 辅助 | 交付物清单与 Bundles 强类型定义                                                                                                                                                                         |
| `ArtifactCard.tsx`                         | 核心 | 聊天卡片；HTML/SVG/Mermaid 默认 inline 渲染；Globe 发布；Wiki ingest（**chat agentConfig.agentId scoped**）；HTML 工件 HITL「推送到公众号草稿」入口；`*.organize-plan.json` HITL 整理计划审阅/执行/回滚 |
| `SkillDetectionCard.tsx`                   | 核心 | 检测工件中 SKILL.md → 打包下载 / 打包注册；注册成功 toast 展示还原的回归门禁用例数（`restored_eval_cases`）                                                                                             |
| `WeChatDraftPanel.tsx`                     | 核心 | 公众号草稿 HITL 面板：author/digest/title/cover、合规命中展示、封面 suggest                                                                                                                             |
| `wechatDraftPanelUtils.ts`                 | 辅助 | 草稿 author/digest clamp、默认标题/作者、合规 hits 归一化                                                                                                                                               |
| `OrganizePlanPanel.tsx`                    | 核心 | workspace organize HITL：校验 dry-run、应用移动、回滚上一 job；Apply/Rollback 后 dispatch workspace-file-changed；Turn Undo 区分 hint；partial rollback 告警                                            |
| `organizePlanUtils.ts`                     | 辅助 | organize-plan.json 解析/编辑/序列化                                                                                                                                                                     |
| `useWechatCoverSuggest.ts`                 | 辅助 | 公众号草稿封面：`GET /files/suggest` debounce + 图片扩展名过滤                                                                                                                                          |
| `wechatDraftCoverUtils.ts`                 | 辅助 | 从 artifact HTML 解析首张本地 `<img>` 供草稿封面预填                                                                                                                                                    |
| `PublishModal.tsx`                         | 核心 | 多 target 发布；target 下拉 + `/publish` + WS + Settings 深链                                                                                                                                           |
| `artifactUtils.ts`                         | 辅助 | preflight/share API、`isPublicationStale`、`publicationsChanged`                                                                                                                                        |
| `ArtifactRenderer.tsx`                     | 核心 | 多类型工件渲染路由；Code/Document/Mermaid/Diff 预览 dynamic import                                                                                                                                      |
| `ReactPreview.tsx`                         | 核心 | React 组件纯预览器（Sandpack）；视图切换由 PortalHeader 统一控制                                                                                                                                        |
| `components/SandpackErrorBoundary.tsx`     | 辅助 | Sandpack 编译/运行时错误边界                                                                                                                                                                            |
| `components/CompileErrorDisplay.tsx`       | 辅助 | Sandpack 编译错误展示面板                                                                                                                                                                               |
| `renderers/MediaPreview.tsx`               | 辅助 | `HtmlPreview` 沙箱 iframe; `SvgPreview` DOMPurify 安全渲染; `ImagePreview` 可选 `showEditButton`（workspace 预览禁用编辑上传）                                                                          |
| `renderers/MermaidPreview.tsx`             | 辅助 | Mermaid 图表渲染（Suspense + dynamic import）                                                                                                                                                           |
| `portal/useSelectionAction.ts`             | 辅助 | Artifact 选中交互的通用消息发送 hook（dirtyArtifacts 注入 + Agent 忙碌排队）                                                                                                                            |
| `portal/SelectionToolbar.tsx`              | 辅助 | Monaco Editor 选中文本悬浮操作栏                                                                                                                                                                        |
| `portal/DocumentSelectionToolbar.tsx`      | 辅助 | 文档预览 DOM 选中文本悬浮操作栏                                                                                                                                                                         |
| `portal/ElementPickerToolbar.tsx`          | 辅助 | DOM 元素拾取指令栏                                                                                                                                                                                      |
| `renderers/DocumentPreview.tsx`            | 核心 | 文档/Markdown 渲染预览（集成 DocumentSelectionToolbar）                                                                                                                                                 |
| `renderers/DiffPreview.tsx`                | 核心 | 版本间差异对比渲染器（Monaco DiffEditor，inline/side-by-side 双模式）                                                                                                                                   |
| `renderers/DocxPreview/`                   | 辅助 | Word (.docx) 高保真预览（docx-preview 库渲染，集成 DocumentSelectionToolbar）                                                                                                                           |
| `renderers/PptxPreview/`                   | 辅助 | PowerPoint (.pptx) 幻灯片预览（@aiden0z/pptx-renderer 库渲染）                                                                                                                                          |
| `renderers/SpreadsheetPreview/`            | 辅助 | CSV/TSV/XLSX 表格只读预览                                                                                                                                                                               |
| `renderers/SpreadsheetEditor/`             | 辅助 | XLSX Live 编辑器（Univer Sheet SDK，Edit 模式下可编辑，SheetJS 双向 XLSX 转换）                                                                                                                         |
| `__tests__/largeFileInlinePreview.test.ts` | 测试 | large-file inline preview 文案与阈值回归守卫                                                                                                                                                            |
| `__tests__/useWechatCoverSuggest.test.ts`  | 测试 | 封面 suggest 图片扩展名过滤                                                                                                                                                                             |
| `__tests__/wechatDraftPanelUtils.test.ts`  | 测试 | author/digest clamp、默认标题/作者                                                                                                                                                                      |
| `__tests__/wechatDraftCoverUtils.test.ts`  | 测试 | 文内首图 `src` 解析（本地路径 / 跳过远程）                                                                                                                                                              |
| `__tests__/organizePlanUtils.test.ts`      | 测试 | organize-plan 文件名检测与 JSON 编辑工具                                                                                                                                                                |

---

## 依赖关系

- `@/services/hosting.ts`：targets CRUD、publish、publications、WS URL
- `@/lib/api`：artifact GET
- `@/lib/constants/artifact`：`LARGE_FILE_THRESHOLD` 等工件系统配置常量
- `@/store/chat`：`publications[]` 同步
- `app/api/files/hosting_api.py`、`artifact_share_api.py`（服务端）
