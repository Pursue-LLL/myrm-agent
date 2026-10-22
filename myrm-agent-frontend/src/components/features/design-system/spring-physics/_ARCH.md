# 物理弹性曲线、微交互设计规范与高质感产物美学雕琢套件架构清单

| 文件 | 类型 | 职责描述 | 状态 |
| :--- | :--- | :--- | :--- |
| `springPhysicsTokens.ts` | 契约定义 | 自然阻尼物理弹簧曲线 SSOT、四大品牌动效人格、五车道选型矩阵、4px/8px 网格与 GPU 安全校验 | 稳定生效 |
| `useSpringPhysics.ts` | 状态机 | 微交互物理弹簧 Hook，响应悬停、按压物理回弹，并支持 prefers-reduced-motion 语义保留降级 | 稳定生效 |
| `InteractiveSpringButton.tsx` | UI组件 | 工业级四态物理弹簧按钮，支持全状态微动效、键盘无障碍焦点环与品牌动效人格 | 稳定生效 |
| `SpringCard.tsx` | UI组件 | 高质感物理弹性卡片容器，集成细致高光边框、微悬停抬升与自然阻尼回弹 | 稳定生效 |
| `DesignSystemGridGuide.tsx` | UI组件 | 动效人格实时体验面板、4px/8px 空间网格排版自检与五车道选型路由展示 | 稳定生效 |
| `index.ts` | 统一出口 | 聚合导出微交互动效物理学所有类型定义、Hook 与核心视图组件 | 稳定生效 |
