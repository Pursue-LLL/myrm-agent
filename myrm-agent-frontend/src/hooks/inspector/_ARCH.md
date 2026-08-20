# inspector/

## 架构概述

Desktop / Browser Inspector（agent 控制镜像）的 React Hook 层。与 store 交互的纯编排逻辑在 [lib/inspector/_ARCH.md](../../lib/inspector/_ARCH.md)，本目录只放 hook。

## 文件清单

| 文件                                          | 地位 | 职责                                                                                  | I/O/P |
| --------------------------------------------- | ---- | ------------------------------------------------------------------------------------- | ----- |
| `useClosePanelOnChatSwitch.ts`                | 核心 | chatId 切换时关闭 Inspector 面板（避免 TOOL_START 携带旧 sourceChatId 误关闭/误打开） | ✅    |
| `__tests__/useClosePanelOnChatSwitch.test.ts` | 测试 | chatId 不变不关；切换时关闭；空 chatId 跳过                                           | —     |

## 依赖

- `@/store/*` — inspector store（由调用方传入 closePanel）
- 消费者：`DesktopInspectorToggle`、`DesktopLiveView`、`BrowserLiveView`
