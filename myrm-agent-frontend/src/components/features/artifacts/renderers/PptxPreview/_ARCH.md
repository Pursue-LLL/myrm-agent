# PptxPreview/

演示文稿（`.pptx`）高保真预览：拉取存储 URL 二进制后由 `@aiden0z/pptx-renderer` 渲染可翻页幻灯片。

| 文件 | 职责 |
|------|------|
| `index.tsx` | 加载/错误态、幻灯片导航（prev/next）、`PptxViewer` 生命周期 |

## 依赖

- `@aiden0z/pptx-renderer` — PPTX → HTML/SVG
- `@/lib/api::getStorageUrl` — 存储 URL 构建
- `useTranslations('artifacts')` — 错误文案
