# quad-graph/

## 架构概述

四图分层动态拓扑视界与可观测图控制台 (`QuadGraphMultiLayerExecutionCanvasAndTopologyInspectionHUD`, Item 50 P0)。
提供 Task Graph (任务全景)、Workflow Graph (算子流道)、Team Graph (专家团队)、Communication Graph (即时通信) 的四重视角平滑切换、节点五态光晕流式渲染、因果依赖缩放与点击即时下钻 (Live Steer / Pause / Retry / Receipt) 驾驶舱。

## 文件清单

| 文件名 | 类型 | 职责 | 状态 |
| :--- | :--- | :--- | :--- |
| `quadGraphTypes.ts` | 类型 | 领域契约（GraphLayerType、NodeStatus、GraphNode、GraphEdge、NodeSteerPayload 等） | ✅ |
| `useQuadGraphStore.ts` | 状态 | Zustand 状态机（当前活跃层级、节点/边池、选中下钻、五态光晕、实时 Steer 指令派发与摘要统计） | ✅ |
| `GraphViewportSwitcher.tsx` | 组件 | 顶部四重视角切换 TAB 栏，附带动态节点数量徽标与无障碍支持 | ✅ |
| `NodeInspectionDrawer.tsx` | 组件 | 节点下钻详情抽屉（耗时/角色/依赖、输入快照、输出 Receipt、实时 Steer 输入与暂停/恢复/重试） | ✅ |
| `QuadGraphExecutionCanvas.tsx` | 组件 | 主控拓扑执行画布（平滑缩放、分层节点高亮渲染、因果连接指向线、底部度量指标栏与抽屉集成） | ✅ |
| `index.ts` | 门面 | 统一导出所有类型、组件与 hook | ✅ |

## 依赖关系

- 内部：`./quadGraphTypes`、`./useQuadGraphStore`、`./GraphViewportSwitcher`、`./NodeInspectionDrawer`
- 外部：`lucide-react`、`next-intl`、`zustand`
