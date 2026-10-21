# Single-Pass RichStream & ElasticSlots Architecture

## 职责边界
- `streamProtocolTypes.ts`: 单遍富文本 Span、强类型流式组件块与弹性视口强类型声明；
- `singlePassRichTextEngine.ts`: 纯函数单遍线性推导引擎，提供 O(N) 粗体/行内代码/ANSI 色彩解析与基准吞吐测速；
- `elasticSlotsStateMachine.ts`: 基于 TLA+ 形式化建模验证的视口自适应重锚定、用户分离与虚拟槽位状态机；
- `useStreamProtocolStore.ts`: Zustand 状态总线，管理高吞吐流式增量合并、视口推进与实时性能指标；
- `SinglePassRichStreamViewer.tsx`: 高性能强类型流式渲染视图组件，杜绝危险 HTML 注入并支持平滑底部锚定；
- `StreamPerformanceBenchmarkModal.tsx`: 实测对比单遍流式引擎 vs 传统 O(N²) 正则重排的延时加速与 CPU 负载表现。
