# Item 122: InteractiveCalloutAnchorAndVisualEvidenceBindingSuite 架构设计

## 1. 核心定位与业务价值
彻底破除用户在阅读智能体输出的长篇代码审计、工程排障或多模态分析报告时，文字描述与右侧工件视口（Canvas/DOM/3D）割裂的硬伤体验。通过空间引文锚点协议（Callout Anchor Protocol）与双向聚焦矩阵算法，实现“点击左侧引文芯片平滑飞越右侧构件、点击右侧构件反向平滑定位左侧论证段落”的真正一体化空间联动。

## 2. 核心架构与模块划分
- `calloutAnchorTypes.ts`: 空间锚点描述符（CalloutAnchor）、几何包围盒（CalloutBoundingBox）、证据类型（dom/canvas/3d/code）、严重等级与视口变换矩阵。
- `calloutCoordinateMath.ts`: 纯算法空间视口居中变换计算引擎。根据构件目标包围盒计算居中平移矩阵 (translateX, translateY) 与自适应缩放比 (scale)，支持碰撞检测。
- `useCalloutAnchorStore.ts`: Zustand 集中式状态管理与全局事件总线。管理锚点名册、双向选择同步、脉冲动画状态与 `myrm:callout-focused` 全局事件广播。
- `InteractiveCalloutChip.tsx`: 嵌入式交互引文芯片，支持悬停高亮与点击飞越，具备明确的严重性视觉语义与 a11y 原生交互标签。
- `VisualEvidenceCanvasViewport.tsx`: 工件视口构件图谱渲染视窗，平滑响应 CSS Transform 矩阵变换、脉冲指示环与构件点击反向联动。
- `InteractiveCalloutWorkspaceCard.tsx`: 双栏一体化工作区卡片，左侧报告段落与芯片流，右侧工件视口，底部详细证据上下文卡。
- `index.ts`: 统一聚合导出出口。

## 3. 双向事件流与性能治理
- 左到右（Chat -> Viewport）：点击芯片触发 `focusAnchor(id, 'chip')`，计算目标几何中心后以 `cubic-bezier(0.16, 1, 0.3, 1)` 平滑运镜过渡，并在目标构件上激活动态脉冲环；
- 右到左（Viewport -> Chat）：用户在视口中点击任意构件触发 `focusAnchor(id, 'viewport')`，左侧报告对应章节段落高亮并展示详细证据卡片。
- 全量计算均在客户端内存毫秒级运行，零服务端往返延迟。
