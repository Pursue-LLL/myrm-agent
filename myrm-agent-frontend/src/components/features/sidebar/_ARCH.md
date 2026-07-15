# sidebar/

## 架构概述

会话侧栏：项目、会话列表、搜索与拖拽排序。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BatchOperationBar.tsx` | 组件 | 批量操作栏：会话批量选择、移动、删除、导出 ZIP（MD/JSON/HTML 格式选择 + 进度条 + 取消） | ✅ |
| `ChatHistoryList.tsx` | 核心 | 会话历史列表：搜索过滤、日期分组、无限滚动、DnD pin 排序、Fork/Handoff/自动化等操作编排 | ✅ |
| `ChatHistoryRow.tsx` | 核心 | 单行会话条目：右键菜单（Pin/Fork/Handoff/Automation/MoveToProject/Rename/Export/Print/Delete） | ✅ |
| `HandoffDialog.tsx` | 组件 | 会话 Handoff 到其他 Agent/设备的确认对话框 | ✅ |
| `MobileDragButton.tsx` | 辅助 | 移动端侧栏拖拽排序手柄 | ✅ |
| `ProjectBar.tsx` | 核心 | 项目切换与创建顶栏 | ✅ |
| `Sidebar.tsx` | 核心 | 侧栏根容器：宽度响应式、折叠态与键盘导航 | ✅ |
| `UserMenu.tsx` | 组件 | 用户菜单（Settings、批量优化 `userMenu.batchOptimization`→`/batch-optimization`、Brain Console 等） | ✅ |
| `constants.ts` | 辅助 | 侧栏布局与 DnD 常量 | ✅ |
| `dateGroupUtils.ts` | 辅助 | 会话按 Today/Yesterday/Earlier 分组纯函数 | ✅ |
| `useBatchMode.ts` | Hook | 批量选择模式开关与选中 ID 集合 | ✅ |
| `useChatActions.ts` | Hook | 会话 Pin/Rename/Delete/Export/Print 等 imperative 动作 | ✅ |
| `useSidebarState.ts` | Hook | 侧栏展开/折叠、搜索词、滚动位置持久化 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
