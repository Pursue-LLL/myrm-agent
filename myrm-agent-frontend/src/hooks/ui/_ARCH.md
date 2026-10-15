# hooks/ui/

通用 UI 行为 hook（无业务域耦合）。

| 文件                                               | 职责                                                                                                           |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `useMediaQuery.ts`                                 | 响应式断点                                                                                                     |
| `useResizableSidebar.ts`                           | 可拖拽侧栏                                                                                                     |
| `useDividerSelfLimiting.ts`                         | 弹性布局 Divider 测量协商自限 Hook（3 次迭代自限 + 像素级几何收敛阻尼，杜绝 React #185 无限递归崩溃）           |
| `useScrollLock.ts` / `useScrollPositionRestore.ts` | 滚动锁与 AutoScrollFollowPersistenceMirror 滚动跟随持久化镜像总线（L1内存+L2存储双模镜像，支持原生与虚拟滚动） |
| `useVisibilityThrottling.ts`                       | 页面 hidden 时节流                                                                                             |
| `useDragDrop.ts`                                   | 拖拽                                                                                                           |
| `useDndAccessibility.ts`                           | @dnd-kit 拖拽站点共享的屏幕阅读器无障碍层：`useDndAccessibility(labelOf)` 产出 DndContext 的 `accessibility`（本地化的键盘操作说明 + 用标题 / 列名而非内部 id 的实时播报；拾起后 dnd-kit 立刻派发的起点悬停事件不播报，保住「已拾起」），`useDndItemLabels()` 提供拖拽项的 `aria-roledescription` 与手柄 `aria-label`；文案在 `common.dnd`；五个拖拽站点（看板、服务商列表、排队消息、目标队列、置顶会话）已接入，`dndAccessibilityCoverage` 测试静态扫描，新增站点漏接会失败 |
| `useDirtyGuard.ts`                                 | 未保存离开守卫                                                                                                 |
| `useFocusedMode.ts`                                | 专注模式                                                                                                       |
| `useTrafficLightInsets.ts`                         | macOS 桌面端沉浸式窗口交通灯安全区留白自适应（自动注入 `--traffic-light-inset-*` CSS 变量）                    |
| `useModelCheckbox.ts`                              | 模型多选 checkbox                                                                                              |
| `useReactPreview.ts`                               | React 预览                                                                                                     |
