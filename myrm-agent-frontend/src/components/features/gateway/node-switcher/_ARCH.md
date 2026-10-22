# Item 118: MultiNodeGatewaySwitcherSuite 架构设计

## 1. 核心定位与业务价值
针对拥有多台宿主机/工作站（如 Office Mac Studio M2 Max、Home Linux RTX 4090、Cloud H100 等）的重度 Agent 用户，提供瘦客户端层面的无缝网关多节点纳管、健康心跳探测、硬件指纹识别与热切换能力。

## 2. 核心架构与模块划分
- `gatewayNodeTypes.ts`: 节点状态机（healthy/unreachable/degraded/checking/offline）、硬件指纹模型（GPU、RAM、CPU、OS）及事件总线载荷。
- `gatewayHealthProbe.ts`: 节点探活引擎。支持 URL 清洗、超时熔断（AbortSignal）、RTT 延迟计算与节点排序。
- `useGatewayNodeStore.ts`: Zustand 集中式状态管理与持久化。封装节点增删改查、平滑热切换及全局 `gateway:switch` 广播。
- `GatewayNodeSwitcherCard.tsx`: 交互式 UI 卡片。包含当前连接节点状态胶囊、节点名册、快捷切换、手动重新探活及新增节点模态弹窗。
- `index.ts`: 模块聚合导出出口。

## 3. 安全上下文与网络适配
- 针对局域网非 HTTPS 节点（如 `http://192.168.x.x:8000`）提供清晰的可视化提示与安全降级指引。
- 端点格式经过安全正则白名单与 URL 规范化过滤，防止跨站脚本与协议混淆注入。
