# 分布式机队实时协同拓扑流转图与观察者导演驾驶舱架构清单

| 文件 | 类型 | 职责描述 | 状态 |
| :--- | :--- | :--- | :--- |
| `fleetObserverTypes.ts` | 契约定义 | 机队跨机节点、工单流转链路、会商收敛度度量与导演指令契约 | 稳定生效 |
| `useFleetObserverStore.ts` | 状态机 | 机队节点生命周期、工单传递链路进度、会商收敛度追踪与导演指令下发状态机 | 稳定生效 |
| `FleetTopologyCanvas.tsx` | UI组件 | 分布式机队动态拓扑画布，展示 Mac/Cloud/GPU 节点状态、燃烧率与工单流向 | 稳定生效 |
| `FleetDeliberationGauges.tsx` | UI组件 | 会商收敛度指数、反闲聊去冗余比率、Token 实时燃烧速率微监控看板 | 稳定生效 |
| `FleetDirectorConsole.tsx` | UI组件 | 观察者全局控制台，支持一键暂停、单步步进、人类最高仲裁指令注入与干预审计流 | 稳定生效 |
| `index.ts` | 统一出口 | 聚合导出机队协同观察者驾驶舱所有契约类型、状态机 Hook 与视图组件 | 稳定生效 |
