# memory-section/

## 架构概述

设置 → 记忆面板（[`../MemorySection.tsx`](../MemorySection.tsx)）的实现。外壳只持有标签页与对话框开关，并按登录 / 记忆开关状态编排；数据加载、导入导出、记忆操作各有一个 hook，界面按区域拆成组件，文件解析与提示这类纯逻辑不依赖 React。

几条贯穿的约束：

- 搜索框文本由外壳层的 `useMemoryTabData` 持有：离开“全部”页再回来，输入内容还在，且与 store 里的查询保持一致；输入停顿 300 ms 才写入 store，离开“全部”页时尚未生效的输入不会写入。
- 导入先 dry-run 预检再弹审阅框：`pendingImport` 同时承载预检结果、预检 ID 与过期时间，审阅框开着当且仅当它存在；确认成功后刷新记忆列表，失败时保留审阅框。
- 导出 JSON 经共用的 `triggerDownload`：桌面端走系统保存对话框，用户取消保存不提示成功。
- 软删除的语义 / 情景记忆给出撤销入口；清空全部记忆成功后重新检查向量库孤儿集合，让迁移提醒与实际数据一致。
- 未登录或鉴权未就绪时不加载任何数据，即使 `?tab=` 深链指向“全部”或“回收站”。

## 文件清单

| 文件                       | 地位 | 职责                                                                                                                                                 | I/O/P |
| -------------------------- | ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `memoryImportFile.ts`      | 逻辑 | 无 React 的导入文件解析：50 MB 体积上限判断；`.jsonl`（Claude Code 会话）逐行解析并跳过空行 / 损坏行，没有有效行时报错，其余文件按单个 JSON 文档解析 | ✅    |
| `memoryNotices.ts`         | 逻辑 | 无 React 的提示：失败提示带错误原文（没有原文用通用兜底）；导入结果按就绪态给出成功 / 警告 / 严重提示，首个问题有设置页入口时改用带操作按钮的提示    | ✅    |
| `useMemoryTabData.ts`      | 辅助 | 当前标签页的数据加载（待确认 / 全部 + 热门标签 / 回收站）、搜索框 300 ms 防抖入库、手动刷新；登录与鉴权就绪后才加载                                  | ✅    |
| `useMemoryImportExport.ts` | 辅助 | JSON / Markdown 导出，以及“选文件 → 预检 → 审阅确认”导入流程的状态与动作；每次选文件后清空 input，同一文件可再次选择                                 | ✅    |
| `useMemoryActions.ts`      | 辅助 | 单条记忆的删除（含撤销）、启停、保护、转入对话，以及清空全部的确认状态与动作                                                                         | ✅    |
| `MemoryHeader.tsx`         | 组件 | 标题、使用指南入口、说明文案，以及记忆开启但向量模型未生效时的关键词检索模式提示                                                                     | ✅    |
| `MemoryToolbar.tsx`        | 组件 | 右上角图标工具栏：导入 / 导出 / 导出 Markdown / 分享规则 / 刷新 / 新建 / 清空；清空按钮悬浮时使用 destructive 文本色                                 | ✅    |
| `MemoryListFilters.tsx`    | 组件 | “全部”页的搜索框、类型筛选（带说明提示）、排序字段与方向、热门标签筛选（最多 10 个）                                                                 | ✅    |
| `MemoryAllTab.tsx`         | 组件 | “全部”页：筛选控件 + 加载中 / 空态 / 记忆卡片网格 + 加载更多                                                                                         | ✅    |
| `MemoryTrashTab.tsx`       | 组件 | “回收站”页：还原 / 彻底删除 / 加载更多接到 store，并给出结果提示                                                                                     | ✅    |

## 测试

`__tests__/memorySectionTestKit.tsx` 提供共用的模块 mock（store、接口、提示、子组件替身）、可变状态与交互 helper（假时钟来自 `@/test-utils/fakeClock`，延迟 Promise 来自 `@/test-utils/deferred`），`memorySectionFixtures.ts` 是数据夹具，`memorySectionStubs.tsx` 是子组件替身。`memoryImportFile` 覆盖文件解析；`MemorySectionLayout` 覆盖登录 / 开关编排、标签页数据加载与深链、搜索防抖与对话框开关；`MemorySectionAllTab` 覆盖列表状态、筛选排序与单条记忆操作；`MemorySectionImportExport` 覆盖导出与选文件预检；`MemorySectionImportConfirm` 覆盖审阅确认与导入后的就绪态提示；`MemorySectionTrashAndClear` 覆盖回收站与清空全部。

## 依赖

- `@/store/memory`、`@/store/useConfigStore`、`@/store/useAuthStore`、`@/store/useRetrievalStore`、`@/services/memory`（含 `archive`）、`@/components/features/memory/*`
- 同级 [`../MigrationWizardReadiness.ts`](../MigrationWizardReadiness.ts)（导入就绪态文案）
- 父模块 [`../_ARCH.md`](../_ARCH.md)
