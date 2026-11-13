# research/ 模块架构

## 架构概述

Research 三栏研究工作台 GUI（入口：侧栏「更多」→ `/research`）。左栏资料池、中栏 ChatWindow 对话、右栏工件输出。研究区容器宽度 ≥ 72rem 三栏并列，更窄时 Tab 单栏。

## 文件清单

| 文件                      | 地位 | 职责                                                                                                                                                                                                                                                   | I/O/P |
| ------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----- |
| `ResearchLayout.tsx`      | 核心 | 三栏布局容器：容器宽度 ≥ 72rem（`@6xl`）三栏并列、分割线可拖拽且中栏不窄于 420px；更窄时三栏仍全部挂载、只显示当前 Tab 的一栏；每栏 `contain-layout`，使聊天里 `position: fixed` 的输入坞与徽标限定在本栏；Vitest：`__tests__/ResearchLayout.test.tsx` | ✅    |
| `ResourcePoolPanel.tsx`   | 核心 | 左栏资料池（Wiki 概念搜索 + 文件上传 + checkbox 勾选，行内按钮的无障碍名称带资源名且已本地化）；Vitest：`__tests__/ResourcePoolPanel.test.tsx`                                                                                                         | ✅    |
| `ResearchOutputPanel.tsx` | 核心 | 右栏工件输出（复用 ArtifactRenderer + PortalTabs + 下载/存 Wiki，**chat agentConfig.agentId scoped ingest**）；Vitest：`__tests__/ResearchOutputPanel.scope.test.tsx`                                                                                  | ✅    |
| `useResearchSync.ts`      | 辅助 | 勾选资料 → ChatStore mentionReferences 同步 Hook                                                                                                                                                                                                       | ✅    |

## 依赖

- `@/store/useResearchStore` — Research 全局状态（资料勾选、面板切换）
- `@/store/useChatStore` — 聊天状态（mentionReferences 注入，removeMentionReferencesByTypes 按类型清理；**Wiki ingest agent scope**）
- `@/components/primitives/tabs` — 窄容器下的三栏 Tab 切换
- `@/store/useArtifactPortalStore` — 工件 Portal 状态（selector hooks）
- `../chat-window/ChatWindow` — 聊天主组件（dynamic import）
- `../artifacts/ArtifactRenderer` — 工件渲染器
- `../artifacts/portal/PortalTabs` — 工件标签页
- `@/services/wikiService` — Wiki API
- `@/services/file` — 文件上传 API

## 约束

- 三栏与 Tab 的切换看研究区自身的容器宽度（`@container`，72rem），不看视口：`AppLayout` 给 `/research` 满幅、`h-dvh` 的页框（不套 `max-w-screen-lg`、不挂内容侧栏）；<`lg` 时 Tab 条左侧让出悬浮侧栏开关（`max-lg:pl-14`）
- 中栏 ChatWindow 的输入坞是视口固定定位，只靠各栏的 `contain-layout` 留在中栏内，不要去掉；主题场景表（`theme-engine/readability-scene`）已把 `/research` 归为功能页
- 资料同步通过 `useResearchSync` 在 effect 中操作 ChatStore，仅管理 `wiki_concept`/`wiki_raw_file` 类型引用，不影响用户手动 @ 的其他引用
- 不修改 ChatWindow 或 ArtifactPortal 内部逻辑，仅通过组合复用
- Chat→Wiki 写入三入口 SSOT：`SaveToWikiButton`、`ArtifactCard` ingest、`ResearchOutputPanel` ingest 均传 `useChatStore.agentConfig.agentId`
