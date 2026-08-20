# DocxPreview/

Word（`.docx`）高保真预览：拉取存储 URL 二进制后由 `docx-preview` 渲染为带样式 HTML，集成 `DocumentSelectionToolbar` 支持选中文本→AI 操作。

| 文件        | 职责                                                          |
| ----------- | ------------------------------------------------------------- |
| `index.tsx` | 加载态/错误态 + `renderAsync` 挂载到容器 + 选中文本悬浮工具栏 |

## 依赖

- `docx-preview` — DOM 渲染
- `@/lib/api::getStorageUrl` — 存储 URL 构建
- `useTranslations('artifacts')` — 错误文案
- `portal/DocumentSelectionToolbar` — 选中文本悬浮操作栏（modify/explain/optimize/copy）
