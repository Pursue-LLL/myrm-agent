# UnifiedMultiTabWorkbenchAndInPlacePartialChunkRefinementSuite 架构设计

## 1. 核心定位
本套件解决用户与 AI 协作时在多视窗（聊天/浏览器/本地文档/终端）反复切换割裂，以及面对长文本/代码仅需微调局部却被迫整篇重新生成导致 Token 与时间海量浪费的问题。

## 2. 模块分层
- `workbenchTypes.ts`: 全要素资源（Document, Browser, Terminal, Code）、多标签、划选范围、就地重构任务与算力节约指标契约；
- `partialRefinementEngine.ts`: 纯算法层，支持选区上下文提取、基于偏移量/子串的原子就地安全替换、Token 节约率估算与启发式微调生成；
- `useWorkbenchStore.ts`: Zustand 状态管理中心，管控多标签生命周期、活跃资源、鼠标划选、局部重构任务状态机及全局事件派发；
- `InPlacePartialRefinementPopover.tsx`: 划选就地局部重构编辑微 Prompt 浮层，支持自然语言输入、AST/Text 差量实时预览与原子采纳；
- `WorkbenchResourceViewers.tsx`: 4 类核心资源交互渲染器，内嵌选区捕获与沙箱控制台；
- `UnifiedMultiTabWorkbench.tsx`: 侧边工作台主容器，支持侧边栏停靠、加宽展开、多标签切换增删与累计算力节约看板。
