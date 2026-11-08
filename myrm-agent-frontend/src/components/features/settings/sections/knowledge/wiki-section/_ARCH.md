# wiki-section/

## 架构概述

设置 → 知识库面板（[`../WikiSection.tsx`](../WikiSection.tsx)）的实现。外壳只把各层 hook 与卡片组合起来并给出标签页框架；状态与动作分在七个 hook（范围、导航、目的、总览数据、问答、维护、导入），界面按卡片拆成组件，时间与跳过原因的格式化是不依赖 React 的纯函数。

几条贯穿的约束：

- 范围只由 URL 的 `agentId` 决定：每次范围变化修订号加一，让按范围缓存的概念列表重新挂载，问答区同时清空上一次的回答、片段与相关文章。
- 标签页以 URL 为准：`wikiTab` / `conceptPath` 进入对应页签，切换标签页回写 URL；`rawPath` 与 `conceptPath` 分别驱动原文树与概念列表的高亮。
- 回到总览页或范围变化时重读统计；ingest 快照要求刷新时重读统计与原文树；本页触发的编译在队列排空后只提示一次完成。
- 手动编译只把原文入队并唤醒后台 worker；“编译中”以队列的 processing 为准，编译进行中不允许启动维护与重建索引。
- 导入成功后重读统计并切到重复审核页；命中冲突时保留重试信息，用户选择“覆盖”后以 supersede 重试，重试结果不再弹冲突框；迁移向导交接的 Obsidian vault 路径只在首次进入时自动导入一次。
- 被风控拦下的提问只出统一提示，不叠加“查询失败”。
- 本地开发域名（127.0.0.1 / localhost）挂有供 E2E 注入统计与健康报告的桥，部署域名上不挂；`e2e_warm_platform_readiness` 打开时，统计与健康报告先走 `fetch` 回退。

## 文件清单

| 文件                          | 地位 | 职责                                                                                                                       | I/O/P |
| ----------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------- | ----- |
| `types.ts`                    | 类型 | `/wiki/stats` 返回的知识库统计 `WikiStats` 与证据抽屉的展示状态 `WikiSnippetDrawerState`，各模块共用                       | ✅    |
| `wikiStatsFormat.ts`          | 逻辑 | 无 React 的展示格式化：ISO 时间 → 本地化的日期 + 时间（解析失败原样返回）；维护被跳过的原因 → 徽标文案                     | ✅    |
| `useWikiScope.ts`             | 辅助 | 智能体范围（`agentId` / 证据上下文键 / 范围名称）、可选智能体列表与范围修订号，以及切换范围、前往知识图谱的动作            | ✅    |
| `useWikiTabs.ts`              | 辅助 | 当前标签页与 URL 的双向同步，跨页签跳转（概念、健康问题、待审综合、重复审核）、待审页初始筛选与 `focus=wikiignore` 滚动    | ✅    |
| `useWikiPurpose.ts`           | 辅助 | “目的 / 方向”文本：已保存值与草稿分开，范围变化时重读，保存动作                                                            | ✅    |
| `useWikiOverviewData.ts`      | 辅助 | 统计、健康报告、原文树、编译运行与 ingest 快照的加载与重载，及待综合 / 重复组计数；本地开发域名上的 E2E 注入桥             | ✅    |
| `useWikiQuery.ts`             | 辅助 | 问答的输入、结果、证据抽屉状态与提交动作；提交前清空上一次结果，被风控拦下的提问只出统一提示                               | ✅    |
| `useWikiMaintenance.ts`       | 辅助 | 编译 / 恢复编译熔断、维护（结构化 / 完整，可取消）、修复页面类型与发布状态、重建向量索引的状态与动作                       | ✅    |
| `useWikiImport.ts`            | 辅助 | 文件夹 / ZIP / Obsidian 导入、链接与视频导入收尾、冲突 / 安全提示对话框的状态与回调，supersede 重试，迁移向导 vault 交接   | ✅    |
| `WikiScopeHeader.tsx`         | 组件 | 标题、说明与智能体范围选择器（含默认范围，加载智能体列表时禁用）以及范围提示                                               | ✅    |
| `WikiPurposeCard.tsx`         | 组件 | “目的 / 方向”卡：加载中占位，否则显示可编辑草稿；草稿与已保存值不同时才出现“重置”并允许保存                                | ✅    |
| `WikiStatsBadges.tsx`         | 组件 | 统计卡上半部分的状态徽标与三条提示；待综合与重复组徽标是跳转到对应审核页的按钮，重复组拦下编译时用玫红色强调               | ✅    |
| `WikiStatsCard.tsx`           | 组件 | “知识库统计”卡：加载入口、占位、徽标、健康问题、认知索引三格、概念 / 文章 / 原文计数与原文树                               | ✅    |
| `WikiRetrievalTracePanel.tsx` | 组件 | 检索轨迹面板：索引命中、sidecar 目录、种子（最多 6 个）与选中的概念，四类都为空时不渲染                                    | ✅    |
| `WikiSourceSnippetList.tsx`   | 组件 | 问答的证据片段列表：标题、层级徽标、区块、路径、摘录、claim 证据位置与快照状态，资产命中带缩略图，点击把该片段交给抽屉     | ✅    |
| `WikiQueryResults.tsx`        | 组件 | 问答结果：拒答标签（`text-destructive-text`）或置信度、回答正文、检索轨迹、证据片段与相关文章；没有回答时不渲染            | ✅    |
| `WikiQueryCard.tsx`           | 组件 | “问答”卡：检索模式选择、问题输入（回车提交）、提交按钮、问答结果与证据片段抽屉；问题为空或提交中不可提交                   | ✅    |
| `WikiActionsCard.tsx`         | 组件 | “操作”卡：编译熔断暂停横幅、编译阶段条、维护模式选择与提示、编译 / 维护（可停止）/ 修复 / 重建索引按钮与重建索引的错误清单 | ✅    |
| `WikiBatchImportCard.tsx`     | 组件 | “批量导入”卡：文件夹 / ZIP / 链接 / 视频四个入口与隐藏的文件选择器（网页端才有文件夹选择器）；导入进行中禁用全部入口       | ✅    |
| `WikiObsidianImportCard.tsx`  | 组件 | “Obsidian vault 导入”卡（锚点 `wiki-obsidian-import`）：桌面端选 vault 文件夹，所有端可上传 ZIP                            | ✅    |
| `WikiImportDialogs.tsx`       | 组件 | 路径冲突、安全拦截与脱敏、链接导入、视频导入四个对话框的挂载点                                                             | ✅    |

## 测试

`__tests__/wikiSectionTestKit.tsx` 提供共用的模块 mock（`next-intl`、路由、`sonner`、接口、桌面端能力、ingest 订阅与维护运行的可控替身、子面板替身）、可变状态与交互 helper（假时钟来自 `@/test-utils/fakeClock`，延迟 Promise 来自 `@/test-utils/deferred`），`wikiSectionFixtures.ts` 是数据夹具，`wikiSectionStubs.tsx` 是记下 props 的子组件替身，`wikiMaintenanceHarness.ts` 与 `wikiImportBench.tsx` 分别把维护与导入 hook 接上可驱动的宿主，`wikiShellBench.tsx` 渲染整个面板并提供外壳测试共用的断言 helper。

hook 逐层覆盖：`useWikiScope` / `useWikiTabs` / `useWikiPurpose` / `useWikiQuery` 各一份；`useWikiOverviewData` 分为加载与派生、E2E 注入桥与暖平台回退、本地开发域名、部署域名四份；`useWikiMaintenance` 分为编译维护与修复重建两份；`useWikiImport` 分为各来源导入、supersede 重试与提示、迁移交接三份。组件各一份（导入的三张卡共用一份），`wikiStatsFormat` 覆盖纯函数；`WikiSection.shell` 覆盖外壳把各层接起来：范围与标签页框架、总览布局、跳转、vault 动作与其它页签；`WikiSection.scope` 覆盖范围抵达每一层（目的、统计、问答、编译维护、导入）以及加载中的锁定。

## 依赖

- `@/services/wikiService`、`@/services/wiki/evidenceMetrics`、`@/services/agent`、`@/lib/api`
- 同级 [`../useWikiIngestSubscription.ts`](../useWikiIngestSubscription.ts)、[`../useWikiMaintainRun.ts`](../useWikiMaintainRun.ts)、[`../wiki/`](../wiki/_ARCH.md)（对话框、原文树与工具函数）
- 父模块 [`../_ARCH.md`](../_ARCH.md)
