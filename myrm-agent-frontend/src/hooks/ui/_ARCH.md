# hooks/ui/

通用 UI 行为 hook（无业务域耦合）。

| 文件                                               | 职责                                                                                                           |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `useMediaQuery.ts`                                 | 响应式断点                                                                                                     |
| `useResizableSidebar.ts`                           | 可拖拽侧栏                                                                                                     |
| `useDividerSelfLimiting.ts`                         | 弹性布局 Divider 测量协商自限 Hook（3 次迭代自限 + 像素级几何收敛阻尼，杜绝 React #185 无限递归崩溃）           |
| `useScrollLock.ts` / `useScrollPositionRestore.ts` | 滚动锁与 AutoScrollFollowPersistenceMirror 滚动跟随持久化镜像总线（L1内存+L2存储双模镜像，支持原生与虚拟滚动） |
| `useVisibilityThrottling.ts`                       | 页面 hidden 时节流                                                                                             |
| `useScrollEdgeFade.ts`                             | 横向滚动区（不显示滚动条）的边缘渐隐提示：`useScrollEdgeFade()` 回调 ref 跟踪滚动、自身与子节点尺寸、子节点增减，把确有内容被裁的一侧写成 `data-fade-start` / `data-fade-end`，配合 `globals.css` 的 `.scroll-fade-x` 只渐隐那一侧，放得下时不加遮罩（`__tests__/useScrollEdgeFade.test.tsx`） |
| `persistedStringStore.ts`                          | 本机键值记忆的共用内核：`createPersistedStringStore(keyPrefix)` 产出 `read` / `write` / `subscribe`，写入 localStorage `<keyPrefix><key>`；存储拒绝写入（隐私模式 / 配额）的值留在模块内存里并优先于存储，之后一次被接受的写入把权威交还给存储（布尔开关不能读到过期的存储值）；同页写入与跨标签 `storage` 事件（含 `key: null` 的清空）都通知订阅者；读存储抛错按「没有」处理（`__tests__/persistedStringStore.test.ts`） |
| `useProactiveDismissal.ts`                         | 主动推荐卡片（建议条、发现/更新横幅）的关闭记忆，建立在 `persistedStringStore`（前缀 `myrm.proactive.dismissed.`）之上：`dismissProactive(key, { snoozeDays? })` 写入永久或到期时间戳（一次性提议——外部助手导入、PWA 安装——被关闭后统一静默 `OFFER_SNOOZE_DAYS` = 7 天），`isProactiveDismissed` 读取，`useProactiveDismissed` 以 `useSyncExternalStore` 暴露（服务端与水合渲染「未关闭」，客户端再套用真实记忆，无水合不一致）；存储不可用时关闭至少在本页有效（`__tests__/useProactiveDismissal.test.tsx`） |
| `useNoticeSlot.ts`                                 | 空聊天页首屏提示卡的单槽协调：`useNoticeSlot(id, wantsSlot)` 让「发现外部助手数据」「有可用更新」两张卡一次只出现一张——先有内容可展示的先占槽，关闭或卸载后下一张才补上，晚到的卡不会插到已可读的卡上方把整页顶下去（手机首屏 CLS 来源，见 `__tests__/useNoticeSlot.test.tsx`）；队列在模块内、`useSyncExternalStore` 订阅，服务端与水合渲染一律「未占槽」 |
| `useDragDrop.ts`                                   | 拖拽                                                                                                           |
| `useDndAccessibility.ts`                           | @dnd-kit 拖拽站点共享的屏幕阅读器无障碍层：`useDndAccessibility(labelOf)` 产出 DndContext 的 `accessibility`（本地化的键盘操作说明 + 用标题 / 列名而非内部 id 的实时播报；拾起后 dnd-kit 立刻派发的起点悬停事件不播报，保住「已拾起」），`useDndItemLabels()` 提供拖拽项的 `aria-roledescription` 与手柄 `aria-label`；文案在 `common.dnd`；五个拖拽站点（看板、服务商列表、排队消息、目标队列、置顶会话）已接入，`dndAccessibilityCoverage` 测试静态扫描，新增站点漏接会失败 |
| `useDirtyGuard.ts`                                 | 未保存离开守卫                                                                                                 |
| `useFocusedMode.ts`                                | 专注模式                                                                                                       |
| `useTrafficLightInsets.ts`                         | macOS 桌面端沉浸式窗口交通灯安全区留白自适应（自动注入 `--traffic-light-inset-*` CSS 变量）                    |
| `useModelCheckbox.ts`                              | 模型多选 checkbox                                                                                              |
| `useReactPreview.ts`                               | React 预览                                                                                                     |
| `useDesktopContextMenuBridge.ts`                   | 下游桌面原生上下文菜单桥接钩子（`myrm:session-row-contextmenu` 事件派发与 Tauri 桌面端 Native 菜单桥接）          |
