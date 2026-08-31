# components/features/extension-slots/ 模块架构

## 架构概述

声明式扩展插槽系统：提供一套无侵入、解耦的插槽（Slot）契约，支持桌面端与 WebUI 插件在预留交互锚点进行动态注入与挂载。

## 核心契约与文件

| 文件 | 职责 |
| --- | --- |
| `types.ts` | 插槽名称、贡献项契约与 Store 状态定义 |
| `useExtensionSlotStore.ts` | 全局插槽注册中心 Zustand Store |
| `ExtensionSlot.tsx` | 声明式插槽挂载容器组件（按 condition 过滤与 order 排序） |
| `index.ts` | 模块聚合导出出口 |
| `__tests__/ExtensionSlot.test.tsx` | 插槽渲染、优先级排序与条件过滤单元测试 |
