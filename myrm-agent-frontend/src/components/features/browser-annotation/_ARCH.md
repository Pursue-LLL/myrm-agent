# Browser Annotation Module

内置预览浏览器「点选圈批」与 DOM/CSS 元素精准批注系统前端交互模块。
对标 Hermes Desktop Preview Browser Comment Mode 与现代产品设计审查工作流。提供点选与拉框圈选、带编号交互式 Pin 标记、DOM/CSS 结构化特征采集与脱敏、按 DOM 子树分支自动聚合分组与一键注入输入框全链路闭环。

## Files

| File | Role | Description | I/O/P |
| --- | --- | --- | --- |
| `browserAnnotationTypes.ts` | Types | 圈选矩形框、DOM 特征元数据、编号 Pin、子树分组与 Composer 载荷契约定义 | ✅ |
| `domFeatureExtractor.ts` | Core | 绝对 CSS 选择器生成、DOM 敏感数据脱敏、Computed 样式提取与子树分组算法 | ✅ |
| `cropImageCanvasHelper.ts` | Core | 基于 Canvas 2D 的局部高清视口截图裁切与内存安全边界防护 | ✅ |
| `BrowserAnnotationPinMarker.tsx` | UI | 带编号高亮标记徽标、光晕框与原地编辑/删除评论浮窗组件 | ✅ |
| `BrowserPreviewAnnotationOverlay.tsx` | Core | 主圈批画布覆盖层。支持模式切换、鼠标拉框选区、子树聚合感知与一键导出到输入框 | ✅ |
| `browserAnnotationComposerBridge.ts` | Bridge | 跨组件 CustomEvent 广播与输入框 Payload 注入解耦桥接器 | ✅ |
| `index.ts` | Facade | 统一门面导出 | ✅ |

## Dependencies

- `@/lib/utils/classnameUtils` (POS: Tailwind CSS 类名组合)
- `lucide-react` (POS: Pin, Send, Trash2, X, Sparkles, Layers 等轻量矢量图标)

## Integration Points

- 挂载至 In-App Browser 预览窗口（如 `BrowserLiveView.tsx`、`DevPortSplitPreviewer.tsx` 等）上层，形成透明交互圈批视口
- 通过 `myrm:inject-composer-annotation` 事件无缝向输入框（MessageBox）注入高维结构化 Prompt 与裁切快照
