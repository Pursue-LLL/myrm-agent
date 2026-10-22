# streaming-markdown/

## 架构概述

本模块实现高帧率增量流式 Markdown 渲染器、RAF 动态节流与极端高吞吐防掉帧虚拟化引擎（HighFpsIncrementalStreamingMarkdownRendererAndRafThrottler）。
彻底根治超快 Flash 模型狂飙吐字（150-200+ tokens/s）时前端全量重新渲染导致主线程锁死、输入框卡顿掉帧、风扇狂转与页面假死的致命体验缺陷。
借鉴 pi-tui 增量渲染思想，构建 requestAnimationFrame 微任务批处理帧缓冲区、基于虚拟 DOM 块的增量追加流式解析器（Incremental Append Stream Parser）、不可变块 React.memo 冻结快照隔离与极端高负载下自适应文本降级保障。深度吸收 OpenClaw 独家保留 pi-tui 核心精髓并超越。

## 文件组织

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `streamingMarkdownTypes.ts` | Types | 核心数据模型契约（MarkdownBlock, IncrementalParsedStream, RafThrottleOptions, StreamPerformanceMetrics） | [INPUT] 无外部运行时依赖<br>[OUTPUT] 导出类型契约与性能指标定义<br>[POS] 增量流式渲染数据类型事实源 |
| `incrementalStreamParser.ts` | Logic | 增量切块流式解析引擎，区分已闭合不可变块与活跃尾部块 | [INPUT] 累计 Markdown 文本与流式状态标志<br>[OUTPUT] 结构化 IncrementalParsedStream<br>[POS] 增量块级切分核心算法 |
| `useRafStreamThrottler.ts` | Hook | 基于 requestAnimationFrame 的 60fps 帧率节流缓冲区与动态降级判定 | [INPUT] 上游流式文本、流式状态与节流配置<br>[OUTPUT] 平滑 displayedContent 与帧率性能指标<br>[POS] 帧率调度与高频事件归一化 |
| `IncrementalStreamingMarkdownRenderer.tsx` | Core | 高帧率增量流式渲染组件，支持快照隔离、呼吸光标与轻量排版降级 | [INPUT] 原始文本、流式状态与节流参数<br>[OUTPUT] 高性能流畅渲染视图与 HUD 仪表盘<br>[POS] 会话窗口流式渲染主组件 |
| `index.ts` | Facade | 门面统一导出 | [INPUT] 模块内部所有导出<br>[OUTPUT] 统一向外部提供公共 API<br>[POS] 模块对外唯一门面 |

## 外部依赖

- `lucide-react` (Gauge, Activity, Sparkles 统一轻量矢量图标)
- `@/lib/utils/classnameUtils` (Tailwind 类名合并)

## 生产集成点

- 挂载至会话窗口消息气泡流式渲染通路（`ChatWindow.tsx` / `MarkdownContent.tsx`）
- 在极端高并发模型吐字流下无缝平替传统全量 AST 渲染
