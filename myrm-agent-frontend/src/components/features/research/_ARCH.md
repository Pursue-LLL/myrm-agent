# research/ 模块架构

## 架构概述

Research 三栏研究工作台 GUI。左栏资料池、中栏 ChatWindow 对话、右栏工件输出。PC 三栏 + 移动端 Tab 降级。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ResearchLayout.tsx` | 核心 | 三栏布局容器（可拖拽分割线 + 移动端 Tab 降级） | ✅ |
| `ResourcePoolPanel.tsx` | 核心 | 左栏资料池（Wiki 概念搜索 + 文件上传 + checkbox 勾选） | ✅ |
| `ResearchOutputPanel.tsx` | 核心 | 右栏工件输出（复用 ArtifactRenderer + PortalTabs + 下载/存 Wiki） | ✅ |
| `useResearchSync.ts` | 辅助 | 勾选资料 → ChatStore mentionReferences 同步 Hook | ✅ |

## 依赖

- `@/store/useResearchStore` — Research 全局状态（资料勾选、面板切换）
- `@/store/useChatStore` — 聊天状态（mentionReferences 注入，removeMentionReferencesByTypes 按类型清理）
- `@/hooks/useMediaQuery` — 响应式断点 hook（useIsMobile）
- `@/store/useArtifactPortalStore` — 工件 Portal 状态（selector hooks）
- `../chat-window/ChatWindow` — 聊天主组件（dynamic import）
- `../artifacts/ArtifactRenderer` — 工件渲染器
- `../artifacts/portal/PortalTabs` — 工件标签页
- `@/services/wikiService` — Wiki API
- `@/services/file` — 文件上传 API

## 约束

- PC 三栏布局需 `≥ 768px` 宽度；移动端自动降级为 Tab 模式
- 资料同步通过 `useResearchSync` 在 effect 中操作 ChatStore，仅管理 `wiki_concept`/`wiki_raw_file` 类型引用，不影响用户手动 @ 的其他引用
- 不修改 ChatWindow 或 ArtifactPortal 内部逻辑，仅通过组合复用
