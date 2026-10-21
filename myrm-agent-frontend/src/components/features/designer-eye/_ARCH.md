# Designer's Eye UI Element Inspector & Self-Evolution Pipeline

## 架构定位

设计师之眼（Designer's Eye）是面向全站界面的可视化交互审查与代码自进化流水线。用户或设计师通过快捷键（`Cmd+Shift+E` / `Ctrl+Shift+E`）或界面常驻 HUD 开关激活圈选模式，实时捕获 DOM 节点、组件结构、计算样式，沿 React Fiber 树逆向精准反查前端源码文件与代码行号，并在弹窗内提交自然语言吐槽与修改建议。系统直连后端自进化引擎生成沙箱热更任务，并提供灾备检查点一键安全回滚能力。

## 模块清单

| 文件 | 职责 | 行数/规范 |
|---|---|---|
| `domSourceLocator.ts` | DOM 至 React 组件 AST & Fiber 逆向反查定位器：解析 `__reactFiber$` 树提取 `_debugSource` 文件名/行号、提取组件层级链、构建精准 CSS 选择器与候选源文件推断 | `< 300` 行，零 `any`，纯工具函数 |
| `DesignerEyeOverlay.tsx` | 视口悬浮圈选交互 HUD：监听全局按键、计算 DOM 矩形辅助光框、支持修饰键穿透操作、展示组件名与源码文件名行号徽标、提供常驻切换开关与尺寸徽标，消除 Dead Feature Path | `< 310` 行，零 `any`，Tailwind 语义色 |
| `DesignerEyeFeedbackModal.tsx` | 审查诉求模态框：语义化 `<dialog>`、展示选中元素与逆向定位源码文件/行号、多候选文件切换、快捷标签点选、输入 prompt、触发自进化任务与检查点一键回滚 | `< 330` 行，零 `any`，无原生 emoji |
| `index.ts` | 门面导出文件：统一导出 `DesignerEyeOverlay`、`DesignerEyeFeedbackModal` 与 `domSourceLocator` 核心工具及类型 | 统一入口 |
| `_ARCH.md` | 本模块架构说明与文件职责索引 | 符合架构规范 |

## 数据流与自进化闭环

1. **圈选捕获与 Fiber 逆向定位**：`pointermove` 实时计算 `getBoundingClientRect`，调用 `domSourceLocator.extractInspectionFingerprint` 沿 React Fiber 树遍历 `_debugSource`，提取目标组件 TSX 文件与行号，渲染高亮辅助框及包含文件名:行号的定位徽标；
2. **诉求提交与多候选切换**：用户单击目标节点冻结视口，弹出 `DesignerEyeFeedbackModal`，展示定位到的源码文件与候选列表，收集用户自然语言 Prompt 及分类标签，调用 `POST /api/v1/self-evolution/tasks`（携带 `primary_source` 精准文件与行号）；
3. **安全回滚**：任务生成同时记录快照检查点 `chk-*`，提供 `POST /api/v1/self-evolution/recover` 灾备一键恢复。
