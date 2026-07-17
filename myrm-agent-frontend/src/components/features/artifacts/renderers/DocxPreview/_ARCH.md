# DocxPreview/

Word（`.docx`）高保真预览：拉取存储 URL 二进制后由 `docx-preview` 渲染为带样式 HTML。

| 文件 | 职责 |
|------|------|
| `index.tsx` | 加载态/错误态 + `renderAsync` 挂载到容器 |

## 依赖

- `docx-preview` — DOM 渲染
- `@/lib/api::getStorageUrl` — 存储 URL 构建
- `useTranslations('artifacts')` — 错误文案
