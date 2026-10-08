# canvasBus/

## 架构概述

多窗口画布状态同步与流式渲染背压：跨窗口 / 标签页同步会话焦点、画布状态、工具执行与配置事件（优先 `BroadcastChannel`，回退 `window` CustomEvent）；流式 chunk 经 rAF 节流合并，避免高吞吐（>150 tokens/s）下 UI 掉帧。纯 TypeScript，无 React 依赖。

## 子模块

| 路径                                           | 职责                                                                                                                                                                                       |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `multiWindowCanvasStateBus.ts`                 | `MultiWindowCanvasStateBus`（`getInstance` / `publish` / `destroy`）与 `CanvasBusEvent` 判别联合（`SESSION_FOCUS` / `CANVAS_STATE_UPDATE` / `TOOL_EXECUTION_SYNC` / `CONFIG_SYNC`）          |
| `streamBackpressureController.ts`              | `StreamBackpressureController`：`pushChunk` 合并缓冲、`flushSync` / `endStream`、`getMetrics`（合并 chunk 数 / 渲染帧数 / 紧急 flush 数）；配置 `BackpressureConfig`（`targetFps` / `maxBufferedChars` / `maxWaitMs`） |
| `__tests__/multiWindowCanvasStateBus.test.ts`  | 总线单测                                                                                                                                                                                   |
| `__tests__/streamBackpressureController.test.ts` | 背压控制器单测                                                                                                                                                                           |
