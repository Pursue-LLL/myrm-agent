# virtual-message-list/

虚拟化消息列表：高度缓存 + `@tanstack/react-virtual` 渲染。

| 文件                     | 职责                                                                                |
| ------------------------ | ----------------------------------------------------------------------------------- |
| `VirtualMessageList.tsx` | 虚拟列表主组件（集成 useScrollPositionRestore，支持虚拟化滚动镜像持久化与平滑还原；末尾的底部间距是 `../ComposerClearanceSpacer`，高度随浮动输入框变化，所以 `containerRef` 必须是浮动输入框所在的消息列） |
| `useMessageHeights.ts`   | 动态行高测量与缓存                                                                  |
| `index.ts`               | 门面导出（feature 内允许）                                                          |
