# Interactive Prototype Canvas Architecture (`prototype-canvas`)

## 模块定位
负责从需求意图文档（`intent.md` / `*.intent.md` / `*.prototype.json`）动态生成 React/Tailwind 交互高保真原型画布、多设备视口无缝切换（Desktop / Tablet / Mobile）、所见即所得点击圈选批注（Visual Click-and-Comment Annotation）、以及「✨ 批准原型并导出 spec.md」工程规格交接协议（Item 46 P0）。

## 文件职责清单

| 文件名 | 类型 | 职责说明 | 状态 |
| :--- | :--- | :--- | :--- |
| `prototypeCanvasTypes.ts` | 类型 | 领域类型定义：PrototypeViewport, PrototypeAnnotation, PrototypeSpec, PrototypeHandoffPayload, LivePrototypeCanvasProps | ✅ |
| `usePrototypeCanvasStore.ts` | 状态库 | 原型视口模式、点选批注状态机、批注增删改查、以及规格规范 Markdown 固化导出 | ✅ |
| `LivePrototypeSandbox.tsx` | 安全交互沙箱 | 基于严格安全 iframe，注入 Tailwind 与元素拾取垫片（Element Picker Shim），实现跨端双向通信与元素高亮圈选 | ✅ |
| `PrototypeAnnotationOverlay.tsx` | 批注浮层与抽屉 | 悬浮输入气泡条（快捷键 ⌘+Enter 提交）与右侧滑出批注列表管理抽屉 | ✅ |
| `LivePrototypeCanvas.tsx` | 总控画布容器 | 顶部 HUD 控制栏（多端视口、批注模式切换、Handoff 规格固化导出）与原型工作台集成 | ✅ |
| `index.ts` | 门面 | 统一导出类型、状态库与组件 | ✅ |
| `_ARCH.md` | 文档 | 模块定位与架构清单 | ✅ |
