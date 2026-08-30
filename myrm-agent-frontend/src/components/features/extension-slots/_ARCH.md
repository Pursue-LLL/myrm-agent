# components/features/extension-slots/ 架构说明

## 架构定位与职责
[POS]: WebUI 与桌面/插件声明式扩展插槽系统。提供规范化插槽定义、注册中心与渲染容器，实现 Web 与 Desktop 环境无缝同构。

## 文件清单
- `types.ts`: 插槽名称 (`ExtensionSlotName`)、贡献项契约 (`ExtensionSlotContribution`) 与 Store 状态类型。
- `useExtensionSlotStore.ts`: 基于 Zustand 的全局插槽注册中心。
- `ExtensionSlot.tsx`: 声明式插槽挂载容器组件。
- `index.ts`: 模块聚合导出入口。
- `__tests__/ExtensionSlot.test.tsx`: 插槽注册、条件过滤、排序与 fallback 单元测试。
