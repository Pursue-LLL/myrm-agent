# src/content/

MV3 content scripts injected into web pages (selection, clip capture, glow).

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `clip_image_urls.js` | 核心 | srcset/lazy/picture URL 解析 · `MyrmClipImageUrls` global SSOT | ✅ |
| `clip.js` | 核心 | Wiki clip HTML capture + credentialed asset fetch · `clip_to_wiki` message | ✅ |
| `selection.js` | 辅助 | 选中文本转发 Side Panel（manifest 静态注入） | ✅ |
| `glow.js` | 辅助 | Agent 工作视口边缘发光（动态注入） | ✅ |

## 注入顺序

`clip_client.js` 注入：`clip_image_urls.js` → `clip.js`
