# fleetProfile/

## 架构概述

多服务器 Fleet Profile 客户端层：登记 local / homelab / VPS / cloud sandbox 等多个网关档案，运行时零刷新热切换活跃档案，对各档案做 RTT 健康探测，并在离线时缓冲用户动作、恢复后自动回放。纯 TypeScript 单例，无 React 依赖。

## 子模块

| 路径                                    | 职责                                                                                                                                                                                                   |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `fleetProfileManager.ts`                | `FleetProfileManager` 单例：档案 CRUD（`addProfile` / `updateProfile` / `removeProfile` / `listProfiles`）、`switchProfile` 热切换与 `onProfileSwitch` 订阅、`probeHealth` RTT 探测与 `getHealthStatus`、离线队列（`enqueueOfflineAction` / `getQueuedActions` / `flushOfflineQueue`） |
| `fleetProfileTypes.ts`                  | 数据契约：`ServerFleetProfile`、`FleetEnvironmentKind`、`ProfileHealthStatus`、`OfflineQueuedAction`、`FleetSwitchEvent` 与各类监听器类型                                                              |
| `index.ts`                              | 门面：re-export 类型与 `FleetProfileManager`                                                                                                                                                           |
| `__tests__/fleetProfileManager.test.ts` | 管理器单测                                                                                                                                                                                             |
