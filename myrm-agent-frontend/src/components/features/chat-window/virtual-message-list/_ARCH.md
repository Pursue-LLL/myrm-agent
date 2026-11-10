# virtual-message-list/

虚拟化消息列表：高度缓存 + `@tanstack/react-virtual` 渲染。

| 文件                     | 职责                                                                                |
| ------------------------ | ----------------------------------------------------------------------------------- |
| `VirtualMessageList.tsx` | 虚拟列表主组件（集成 useScrollPositionRestore，支持虚拟化滚动镜像持久化与平滑还原；每条搜索高亮只居中一次，记录在页面传入的 `centeredHighlightRef` 里，列表切换形态或流式更新都不会重复居中；末尾的底部间距是 `../ComposerClearanceSpacer`，高度随浮动输入框变化，所以 `containerRef` 必须是浮动输入框所在的消息列） |
| `useMessageHeights.ts`   | 动态行高测量与缓存                                                                  |
| `MessageRow.tsx` | 单条消息行（memo）：压缩摘要行或消息盒子、高亮环、非末条助手消息的分隔线，每次提交后上报实测高度（大于 0 才上报） |
| `useVirtualListScroll.ts` | 滚动监听：向上滚动超过 5px 标记用户手动滚动、回到底部附近（100px 内）向下滚动超过 5px 清除标记；距顶部 200px 内且还有更早的消息时加载更早的消息并补偿 scrollTop；每次滚动防抖 200ms 保存镜像；只订阅翻页用到的三项 store 状态，输入框草稿等无关写入不会让列表重新渲染 |
| `__tests__/virtualListKit.tsx` | 测试共享底座（须先于 `../VirtualMessageList` 导入）：虚拟化器是库、换成窗口可控的替身，滚动镜像、store 与消息行都是真实的；提供手动推进的 requestAnimationFrame 与假定时器（`settle`）、行高测量、`renderList`、滚动容器指标与滚动事件、镜像读写 |
| `__tests__/VirtualMessageList.rendering.test.tsx` | 渲染测试：只渲染虚拟化器给出的行及偏移、总高度、消息盒子序号与末条标记、助手消息分隔线、压缩摘要行、高亮环；滚动容器与加载占位、翻页转圈、输入框草稿写入不重渲染列表、底部间距；行高估算与缓存（用户行更矮、实测优先、零高度忽略、换会话遗忘、同会话保留）与虚拟化器选项 |
| `__tests__/VirtualMessageList.restore.test.tsx` | 恢复与对外句柄测试：阅读位置恢复（上滑与跟随两种、每个会话一次、等消息、无会话 id 不恢复、列表已卸载不再恢复）；交给页面的 jump-to-message / jump-to-bottom（挂载期间可用、卸载收回、标记与保存、缺省句柄时照常工作） |
| `__tests__/VirtualMessageList.scroll.test.tsx` | 滚动测试：流式跟随（上滑后不跟随）、发送消息一次平滑回到底部；滚动监听的 5px / 100px / 200px 边界（6px 起算）、只通知一次、重新挂载监听后以当前位置为基准、被动监听、200ms 防抖、卸载清理；触顶翻页（一页在途不重复请求、排版完成后补偿 scrollTop 保持原位置） |
| `__tests__/VirtualMessageList.highlight.test.tsx` | 搜索高亮测试：下一帧居中并标记读者已上滑、记录居中过的高亮、消息不存在不动、晚到的消息仍能找到、同一条只居中一次、高亮换成另一条再居中、页面已居中的不再重复 |
| `__tests__/useMessageHeights.test.ts` | 行高缓存测试：读写、重新测量取最新、一次清空、跨渲染同一份缓存与稳定回调 |
| `index.ts`               | 门面导出（feature 内允许）                                                          |
