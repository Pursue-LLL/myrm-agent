# components/features/extension-slots/ 模块架构

## 架构概述

声明式扩展插槽（Extension Slots）与动态插件挂载系统。为 WebUI 核心导航区、侧边栏底部操作区与设置面板提供标准挂载点，支持桌面端与插件模块按需挂载原生扩展，并在纯 Web 访问时优雅降级。

## 文件清单

| 文件 | 职责 | POS 状态 |
| --- | --- | --- |
| `types.ts` | 声明式扩展插槽核心类型定义（`ExtensionSlotName`, `ExtensionSlotContribution`, `ExtensionSlotContext`） | ✅ |
| `useExtensionSlotStore.ts` | 基于 Zustand 的全局插槽注册中心 Store，管理动态挂载、按权重排序与注销 | ✅ |
| `ExtensionSlot.tsx` | 声明式插槽挂载容器组件，按 `slotName` 与 `condition` 动态渲染扩展项，支持 `fallback` | ✅ |
| `index.ts` | 模块对外聚合导出入口 | ✅ |
| `__tests__/ExtensionSlot.test.tsx` | 声明式插槽渲染、权重排序、条件判断与注销行为单元测试 | ✅ |

## 依赖关系

- 消费方：`@/components/layout/NavBar.tsx`、`@/components/layout/AppLayout.tsx`
- 内部依赖：Zustand, React, cn
