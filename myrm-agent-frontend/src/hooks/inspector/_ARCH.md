# inspector/

## 架构概述

Desktop / Browser Inspector（agent 控制镜像）的 React Hook 层。与 store 交互的纯编排逻辑在 [lib/inspector/_ARCH.md](../../lib/inspector/_ARCH.md)，本目录只放 hook。

## 文件清单

| 文件                                          | 地位 | 职责                                                                                                                                                  | I/O/P |
| --------------------------------------------- | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `useClosePanelOnChatSwitch.ts`                | 核心 | chatId 切换时关闭 Inspector 面板（避免 TOOL_START 携带旧 sourceChatId 误关闭/误打开）                                                                 | ✅    |
| `__tests__/useClosePanelOnChatSwitch.test.ts` | 测试 | chatId 不变不关；切换时关闭；空 chatId 跳过                                                                                                           | —     |
| `usePanelResize.ts`                           | 核心 | 右侧停靠面板的宽度状态：指针拖拽 + 键盘（左右键/Home/End）调整、范围夹取、localStorage 持久化，并返回完整 separator 语义（role/tabIndex/aria-value*） | ✅    |
| `__tests__/usePanelResize.test.ts`            | 测试 | 持久化恢复与越界忽略；键盘步进/Home/End/夹取/持久化；拖拽夹取与释放持久化；卸载中途清理监听                                                           | —     |

## 依赖

- `@/store/*` — inspector store（由调用方传入 closePanel）
- 消费者：`DesktopInspectorToggle`、`DesktopLiveView`、`BrowserLiveView`、`DeviceLiveView`（`usePanelResize`）
