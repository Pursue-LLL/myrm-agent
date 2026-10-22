# components/features/widget 架构说明

---

## 模块定位

`widget/` 模块实现了面向外部网站、后台系统与 SaaS 控制台的智能体可嵌入小部件（Embeddable Agent Widget）及双向上下文通信桥（Host Context Bridge）（Item 41 P1）。
支持将智能体以悬浮气泡（Floating Bubble）、侧滑抽屉（Slideout Drawer）以及页面内嵌卡片（Inline Container）三大形态嵌入外部宿主系统；并通过跨域安全的 postMessage IPC 桥梁实时同步宿主网页上下文（URL、选中文本、激活表单数据），注入会话 `@host_context` 提示词。提供可视化的单行 `<script>` 嵌入代码生成器。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `widgetTypes.ts` | 类型 | 核心领域类型定义（WidgetDisplayMode、HostContextSnapshot、HostBridgeMessage、EmbedSecurityConfig 等），零 `any` |
| `useWidgetBridgeStore.ts` | 状态 | Zustand 客户端状态库，管理 Widget 展现形态、开闭状态、宿主上下文快照、通信历史与生成器模态框状态 |
| `HostContextBridge.ts` | 核心 | 跨域安全双向 postMessage IPC 通信桥，支持 Origin 白名单/通配符校验、ping/pong 握手、宿主上下文同步与视口通知 |
| `EmbeddableWidgetContainer.tsx` | UI | 多形态智能体展示外壳容器，响应式支持悬浮气泡、侧滑抽屉、内嵌三种展现模式与上下文状态指示芯片 |
| `WidgetGeneratorModal.tsx` | UI | 可视化嵌入代码生成器对话框，支持形态配置、域名白名单限制、主题选择与单行 `<script>` 代码一键复制 |
| `index.ts` | 门面 | 模块对外聚合导出 |
| `_ARCH.md` | 文档 | 模块定位与架构规范索引 |

---

## 依赖关系

- `lucide-react`（纯 SVG 矢量图标）
- `next-intl`（国际化文本）
- `zustand`（前端状态管理）
