# Structural Infinite Canvas & Zero-Token Editing Architecture

## 职责边界
- `infiniteCanvasTypes.ts`: 结构化图层树 (Text/Shape/Container)、视口矩阵、智能选区与免 Token 强契约；
- `canvasLayerEngine.ts`: 纯函数计算屏幕到画布坐标映射、图层矩形碰撞检测、局部重绘上下文提取与无损 SVG 导出；
- `useInfiniteCanvasStore.ts`: Zustand 状态总线，管理图层树、视口平移缩放、就地直编、智能框选与免 Token 计数；
- `InfiniteDesignCanvasViewport.tsx`: 无限画布交互视口，支持双击就地免 Token 改字、图层拖拽挪动与实时网格渲染；
- `CanvasLassoSelectionOverlay.tsx`: 智能局部框选浮层，显示目标/冻结图层数并提供反向 Prompt 注入通道；
- `CanvasToolbarAndExportDeck.tsx`: 模式切换悬浮甲板，集成免 Token 节省计数器与无损矢量 SVG 导出。
