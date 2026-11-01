# artifacts/portal/

工件门户壳层：标签、版本历史、选区工具栏与手势/键盘 hook。

| 文件                                                                                 | 职责                               |
| ------------------------------------------------------------------------------------ | ---------------------------------- |
| `PortalHeader.tsx` / `PortalTabs.tsx`                                                | 门户顶栏（含布局模式切换）与多标签 |
| `VersionHistory.tsx`                                                                 | 版本列表与回滚入口                 |
| `SelectionToolbar.tsx` / `DocumentSelectionToolbar.tsx` / `ElementPickerToolbar.tsx` | 选区与元素拾取                     |
| `usePortalGestures.ts` / `usePortalKeyboard.ts` / `useSelectionAction.ts`            | 交互 hook                          |
| `PortalErrorDisplay.tsx`                                                             | 门户级错误展示                     |

`usePortalGestures` 的 `separatorProps` 给左缘宽度分隔条提供窗口分隔条语义：可聚焦，指针拖拽与键盘（←/→ 每次 20px、Home/End 跳到 320–1200px 边界）都能调宽。
