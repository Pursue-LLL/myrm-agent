# Agent Granular Token Cost Row Transparency & Chat State Snapshot Throttle Architecture

## Overview
Agent 视图行级细粒度 Token/成本透明度透视与会话状态快照防卡顿节流套件，包含：
- `granularCostTypes.ts`: 算力剖析、费率模型、流式增量补丁与节流监控契约；
- `chatSnapshotThrottleEngine.ts`: 成本精确换算器、数量/金额格式化工具与防抖节流批量聚合引擎工厂（`createThrottledSnapshotEngine`）；
- `useAgentGranularCostStore.ts`: Zustand 状态机，驱动 Agent 消耗画像更新、流式 chunk 聚合提交与节流参数微调；
- `AgentGranularCostRow.tsx`: Agent 视图行级组件，提供半透明 Token/成本徽标（如 `32.4k tokens · $0.048`）及悬停细分透视浮层；
- `ChatSnapshotPerformanceMonitor.tsx`: 会话快照防抖节流监控小组件，可视化呈现消除的冗余快照数与 GC 压力削减率。
