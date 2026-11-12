# settings/sections/machines 模块架构

## 架构概述

自托管机群看板与接管面板的前端组件包：机群节点网格（`MyMachinesSection`）、接入弹窗（`ConnectMachineModal`）与接管抽屉（`LiveTakeoverDrawer`），数据来自 `/api/v1/machines`。屏幕画面与握手结果是界面内的模拟：接管抽屉里的视口、光标以及「60 FPS」「WebRTC」数值是固定展示；接入弹窗在复制命令 2.5 秒后直接显示握手成功，并构造一台示例机器交给 `onConnectedSuccess`。这些组件目前没有被任何设置页面引用。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `machinesTypes.ts` | 核心 | 机群节点、指标快照、平台枚举、接入令牌与接管会话强类型契约 | ✅ |
| `machinesService.ts` | 核心 | 机群列表、接入命令、开始与交还接管的接口调用；请求失败时回落到内置的两台示例节点、本地生成的令牌与本地接管会话 | ✅ |
| `ConnectMachineModal.tsx` | 组件 | 接入弹窗：macOS/Linux/Windows 平台切换、接入命令生成与复制，复制 2.5 秒后模拟握手成功 | ✅ |
| `MyMachinesSection.tsx` | 组件 | 机群看板：节点网格、状态徽标、指标快照与活跃任务数 | ✅ |
| `LiveTakeoverDrawer.tsx` | 组件 | 接管抽屉：模拟的屏幕视口与光标，「接管 / 交还」按钮调用接管接口，接管中显示琥珀色边框 | ✅ |
| `index.ts` | 门面 | 统一导出公共类型、服务与交互组件 | ✅ |

## 设计原则

- **请求失败的回落**：`machinesService.ts` 的四个请求在失败时都返回内置示例数据而不是抛错，界面因此不会显示接口错误。
- **纯矢量与零 Any**：全量使用 Lucide SVG 矢量图标，严禁原生 emoji 与 `any` 类型。
