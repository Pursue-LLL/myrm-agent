# components/features/extension-slots/ 模块架构

## 架构概述

声明式扩展插槽系统：为 WebUI 提供解耦的原生能力和插件挂载点，支持多端（Web / Desktop / Cloud）环境自适应与同构渲染。

## 核心能力

1. **类型安全契约 (`types.ts`)**：定义核心预置插槽（`sidebar.footer.action`, `sidebar.header.action`, `chat.header.actions`, `settings.sections`, `navbar.bottom.tools`）与插槽贡献项契约。
2. **全局注册中心 (`useExtensionSlotStore.ts`)**：Zustand 驱动的插件贡献注册表，支持按优先级（`order`）排序与动态条件（`condition`）过滤。
3. **声明式挂载组件 (`ExtensionSlot.tsx`)**：在 WebUI 布局中作为挂载点，无匹配贡献项时优雅回退（`fallback`），零侵入业务代码。

## 文件清单

| 文件                               | 职责                                             |
| ---------------------------------- | ------------------------------------------------ |
| `types.ts`                         | 插槽名称枚举、上下文类型与贡献项接口定义         |
| `useExtensionSlotStore.ts`         | Zustand 插槽注册中心 Store                       |
| `ExtensionSlot.tsx`                | 声明式挂载容器组件                               |
| `index.ts`                         | 模块对外统一导出门面                             |
| `__tests__/ExtensionSlot.test.tsx` | 插槽渲染、优先级排序、条件过滤与注销单元测试套件 |
