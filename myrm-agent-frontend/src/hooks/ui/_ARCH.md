# hooks/ui/

通用 UI 行为 hook（无业务域耦合）。

| 文件                                               | 职责               |
| -------------------------------------------------- | ------------------ |
| `useMediaQuery.ts`                                 | 响应式断点         |
| `useResizableSidebar.ts`                           | 可拖拽侧栏         |
| `useScrollLock.ts` / `useScrollPositionRestore.ts` | 滚动锁与 AutoScrollFollowPersistenceMirror 滚动跟随持久化镜像总线（L1内存+L2存储双模镜像，支持原生与虚拟滚动） |
| `useVisibilityThrottling.ts`                       | 页面 hidden 时节流 |
| `useDragDrop.ts`                                   | 拖拽               |
| `useDirtyGuard.ts`                                 | 未保存离开守卫     |
| `useFocusedMode.ts`                                | 专注模式           |
| `useModelCheckbox.ts`                              | 模型多选 checkbox  |
| `useReactPreview.ts`                               | React 预览         |
