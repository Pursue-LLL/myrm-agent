# components/features/extension-slots/ 模块架构

## 架构概述

声明式扩展插槽系统：为 WebUI 提供无侵入的原生能力挂载点。支持在侧边栏底栏、设置页、头部操作区等位置声明式插入扩展项，在桌面端激活原生特性，在 Web 端自动隐藏或降级。

## 文件清单

| 文件 | 职责 | 状态 |
| --- | --- | --- |
| `types.ts` | 声明式插槽类型定义与贡献项接口 | ✅ |
| `useExtensionSlotStore.ts` | 全局插槽注册中心 Zustand Store | ✅ |
| `ExtensionSlot.tsx` | 声明式插槽挂载容器组件 | ✅ |
| `index.ts` | 模块统一出口 | ✅ |
| `__tests__/ExtensionSlot.test.tsx` | 单元测试 | ✅ |

## 插槽定义规范

- `sidebar.footer.action`: 侧栏底部扩展操作区
- `sidebar.header.action`: 侧栏顶部扩展操作区
- `chat.header.actions`: 会话头部扩展操作区
- `settings.sections`: 设置页扩展区
- `navbar.bottom.tools`: 导航条底部快捷工具区
