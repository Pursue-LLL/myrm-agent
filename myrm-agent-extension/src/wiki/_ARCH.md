# src/wiki/

MV3 extension wiki clip client — REST multipart upload + Settings deep links.

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `clip_client.js` | 核心 | Inject `clip_image_urls.js` + `clip.js` · POST multipart | ✅ |
| `clip_notify.js` | 辅助 | `chrome.notifications` clip outcome · session 存深链 · click/closed 清理 | ✅ |
| `clip_notify_payload.js` | 辅助 | 纯函数 payload 解析（vitest 可测） | ✅ |
| `deep_links.js` | 辅助 | Build Settings Wiki deep links (duplicate review · wikiignore) | ✅ |

## 契约

| 项 | 说明 |
| --- | --- |
| Clip POST | `/api/v1/wiki/clip?agent_id=` optional · `folder_path=""` · `queue_compile=false` |
| Config GET | `/api/v1/extension/clip-agent` — agent scope + `web_ui_origin` |
| Deep links | `{web_ui_origin}/settings?wikiTab=…` when origin seeded |

## 依赖

- `src/content/clip_image_urls.js` — srcset / picture URL SSOT
- `src/content/clip.js` — dynamic inject page/selection HTML capture
- `src/i18n.js` — Chrome `_locales` error strings
- `src/background.js` — context menu delegates clip flow
