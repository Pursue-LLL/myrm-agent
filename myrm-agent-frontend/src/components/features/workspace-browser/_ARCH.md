# workspace-browser/

## 架构概述

工作区内嵌浏览器预览与检查器联动。有两个使用方：侧栏工作区视图（`layout/ChatSidebarContent`）与辅助工作台的文件页（`workbench/tabs/WorkbenchFiles`），二者共用同一套目录树、实时刷新与预览。

## 文件清单

| 文件                       | 地位 | 职责                                                                                                                                                                                                                       |
| -------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `WorkspaceDialogs.tsx`     | 组件 | 工作区文件操作确认对话框（删除确认、移动目标）；Escape 只取消对话框本身                                                                                                                                                    |
| `WorkspaceFileBrowser.tsx` | 核心 | 沙箱文件树浏览器：展开/收起、右键菜单与写操作入口；未扫描到的文件夹（`children: null`）展开时经 `onLoadChildren` 加载，失败以本地化提示并收起；目录右键「AI 整理」或「设为项目根目录」→ 联动聊天与 Project Scoped 边界     |
| `WorkspaceFileTree.tsx`    | 组件 | 目录树行（递归）：文件夹箭头/加载中转圈、图标、大小、@ 引用（与行按钮并列的独立按钮）、行内重命名；只做展示，数据与操作全部来自属性                                                                                        |
| `WorkspaceContextMenu.tsx` | 组件 | 右键菜单（重命名/移动/删除；目录另含 `onOrganize` 与 `onSetProjectRoot` 入口）；贴近点击位置并保持在视口内，点击任意处或 Escape 关闭                                                                                       |
| `WorkspaceFileOps.tsx`     | 组件 | 上传（拖放与按钮）、新建目录、行内重命名、`useWorkspaceFileOps` 状态                                                                                                                                                       |
| `WorkspaceFilePreview.tsx` | 组件 | 选中文件内联预览；文本走行号编辑器与内嵌 Inline Diff 审查；富媒体委托 `RichMediaFilePreview`                                                                                                                               |
| `InlineWorkspaceDiff.tsx`  | 组件 | 工作区代码即时 Diff 对比抽屉/面板                                                                                                                                                                                          |
| `RichMediaFilePreview.tsx` | 组件 | 富媒体（图片/音视频/PDF/Office/SVG）预览分发；`getPreviewKind` 扩展名路由 + `kind` prop 覆盖；图片禁用 artifact 编辑按钮                                                                                                   |
| `useEscapeDismiss.ts`      | Hook | 临时浮层（右键菜单、对话框）的 Escape 关闭：监听 `document` 并终止事件，宿主（如工作台抽屉监听 `window`）不会随之一起关闭                                                                                                  |
| `useWorkspaceFiles.ts`     | Hook | 三部署 agent vault 文件树：首扫两层，更深的文件夹经 `loadChildren` 按需加载，每次刷新都会重读已打开的文件夹；register watch + SSE auto refresh（经 useGlobalEvents）；较旧的扫描结果与切换工作区后才到的文件夹结果一律丢弃 |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
