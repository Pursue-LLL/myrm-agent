# In-Flight Steer & Collapsible Long Task Summary 架构规范

## 模块定位
负责多智能体协同长任务中的运行中动态纠偏、提前叫停保留半成品草稿、时间线顶部活跃子代理泳道监控，以及折叠式脉冲上下文摘要卡片。

## 文件结构与职能

| 文件 | 地位 | 职责 | I/O/P |
|---|---|---|---|
| `inFlightSteerTypes.ts` | 契约层 | 定义活跃子代理泳道数据结构、纠偏预设项与长任务摘要实体 | I: 状态与纠偏负载<br/>O: TypeScript 强类型定义<br/>P: 领域模型类型 |
| `useInFlightSteerStore.ts` | 状态层 | 管理子代理并发泳道状态、下发实时纠偏指令与优雅叫停并保留半成品；操作结果 toast 走 `chat.inFlightSteer.*`（`showI18nToast`，失败时优先展示服务端原因） | I: 泳道注册、纠偏指令与叫停指令<br/>O: 响应式状态、异步动作与多语言 toast<br/>P: 状态机与服务调用桥接 |
| `InFlightSteerPopover.tsx` | 交互层 | 纠偏微型浮层，提供 4 档高频预设方案、自定义纠偏输入与提前叫停操作 | I: 目标子代理实体与用户指令<br/>O: 纠偏下发与卡片关闭<br/>P: 局部 UI 交互 |
| `ActiveSubagentSwimlanesBar.tsx` | 视图层 | 聊天窗口时间线顶部的横向子代理泳道流与状态脉冲指示 | I: 活跃子代理列表<br/>O: 泳道流呈现与纠偏浮层触发<br/>P: 视图组件 |
| `CollapsibleLongTaskSummaryCard.tsx` | 视图层 | 对话流长任务折叠式摘要卡片、进度条与阶段性关键发现展开 | I: 长任务摘要实体<br/>O: 进度柱与折叠/展开视图<br/>P: 视图组件 |
| `index.ts` | 门面层 | 统一对外导出模块内所有类型、状态 Store 与视图组件 | I: 内部子模块<br/>O: 统一外部命名导出<br/>P: 门面聚合 |
