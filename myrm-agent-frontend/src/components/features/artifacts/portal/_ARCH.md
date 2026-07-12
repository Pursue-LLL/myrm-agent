# artifacts/portal/

工件门户壳层：标签、版本历史、选区工具栏与手势/键盘 hook。

| 文件 | 职责 |
|------|------|
| `PortalHeader.tsx` / `PortalTabs.tsx` | 门户顶栏与多标签 |
| `VersionHistory.tsx` | 版本列表与回滚入口 |
| `SelectionToolbar.tsx` / `DocumentSelectionToolbar.tsx` / `ElementPickerToolbar.tsx` | 选区与元素拾取 |
| `usePortalGestures.ts` / `usePortalKeyboard.ts` / `useSelectionAction.ts` | 交互 hook |
| `PortalErrorDisplay.tsx` | 门户级错误展示 |
