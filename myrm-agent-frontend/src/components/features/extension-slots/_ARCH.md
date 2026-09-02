# components/features/extension-slots/ 模块架构

## 架构概述

声明式扩展插槽系统：提供在 WebUI 各核心锚点（如 `sidebar.footer.action`、`navbar.bottom.tools`、`chat.header.actions` 等）无侵入挂载扩展特性的能力，支持条件激活与纯 Web 环境下的优雅降级。

## 文件清单

| 文件 | 职责 |
| --- | --- |
| `types.ts` | 扩展插槽名称枚举、贡献项契约与 Store 接口定义 |
| `useExtensionSlotStore.ts` | Zustand 插槽注册中心，支持动态注册与注销 |
| `ExtensionSlot.tsx` | 声明式插槽挂载容器组件，负责按 order 排序与 condition 校验并渲染 |
| `index.ts` | 模块公开导出入口 |
| `__tests__/ExtensionSlot.test.tsx` | 插槽挂载、条件判断、排序与注销单元测试 |

## 依赖关系

- 依赖 `@/lib/utils/classnameUtils` 处理容器样式
- 供 `@/components/layout/NavBar.tsx` 与 `@/components/layout/ChatSidebarContent.tsx` 声明式引用
