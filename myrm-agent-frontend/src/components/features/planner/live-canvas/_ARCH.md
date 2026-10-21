# Item 119: LiveExecutionPlannerCanvasAndSandboxWebPreviewSuite 架构设计

## 1. 核心定位与业务价值
针对智能体长程多步复杂任务（如意图拆解、数据建模、代码生成、测试门禁与打包部署），打破传统纯文本对话流黑盒交互缺陷，提供带状态跃迁的动态 DAG 拓扑规划画布，并与沙箱前端应用/代码即时渲染视窗联动。

## 2. 核心架构与模块划分
- `plannerCanvasTypes.ts`: 节点状态机（pending/running/validating/completed/failed/skipped）、DAG 拓扑节点与边模型、视口模型（desktop/tablet/mobile）、产物引用模型。
- `plannerDagLayoutEngine.ts`: 轻量级拓扑分层（Kahn 算法演进）与平滑三次贝塞尔曲线（Cubic Bezier Path）生成引擎，纯算法设计零外部重型依赖。
- `usePlannerCanvasStore.ts`: Zustand 集中式状态管理。管理任务流节点更新、当前聚焦节点、沙箱视口模式、分屏/独立视图切换。
- `PlannerDagGraphView.tsx`: SVG 矢量连线与交互式任务节点卡片视图，展示节点状态徽标、执行耗时、工具调用标签与高亮连线。
- `SandboxLivePreviewView.tsx`: 安全隔离沙箱（`iframe` + `sandbox="allow-scripts allow-same-origin"`），集成响应式多视口切换与热重载。
- `LiveExecutionPlannerCanvasCard.tsx`: 顶层组合卡片，支持分屏/单视图切换、全局任务进度追踪与步骤详情展开。
- `index.ts`: 模块统一聚合导出。

## 3. 安全上下文与渲染隔离
- 沙箱代码使用 `sandbox="allow-scripts allow-same-origin"` 进行受控隔离，防止主工作区 DOM 被意外篡改；
- 所有交互状态与图谱坐标计算全部在客户端内存中纯确定性运行，具备极高帧率与响应速度。
