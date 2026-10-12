# Extension UI Subsystem Architecture (`_ARCH.md`)

## 1. 模块定位与职责 (Item 28 · P0)
本子包位于 `src/components/features/extension-ui/`，实现“基于传输无关抽象的通用 ExtensionUIContext 与双向反向 Push 子协议交互引擎”在前端 WebUI / Desktop 侧的高保真交互呈现：
- **反向 Push 交互承载**：接收后端通过反向子协议派发的 `UIRequestItem`（select, confirm, input, editor），以可访问性良好（a11y）的高保真模态浮层呈现在用户视野中心；
- **状态管理与流转**：通过 `useExtensionUIStore` 维护待处理请求队列与输入表单状态，支持多请求排队与响应出队；
- **双向握手闭环**：用户操作后，通过 `submitUIResponse` 或 `cancelUIRequest` 提交结果帧，解除后端 Agent 的挂起状态。

## 2. 核心文件与契约拓扑
| 文件 | 职责与能力 | 核心契约 |
| :--- | :--- | :--- |
| `extensionUITypes.ts` | 强类型数据契约，定义 `UIRequestType`、`UISelectOption`、`UIRequestItem`、`UIResponsePayload` | 严格零 `any` |
| `ExtensionUIModal.tsx` | 模态浮层主组件，动态适配 select（单选列表）、confirm（双态确认）、input（文本框）、editor（多行代码编辑） | React 19，Lucide 图标，支持键盘 Esc/Enter 快捷键 |
| `index.ts` | 子包公共门面导出 | 导出核心组件与数据类型 |

## 3. 设计红线
1. 单文件行数受控在 `< 350 行`；
2. 严格零 `any` 类型注解；
3. 零原生 emoji，全量使用 Lucide SVG 矢量图标；
4. 国际化全面覆盖（`zh.json` 与 `en.json` 的 `extensionUI` 命名空间）。
