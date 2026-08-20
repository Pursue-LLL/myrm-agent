# embeds/providers/

## 架构概述

纯函数 URL 匹配层：将 `https?://` URL 解析为 `EmbedDescriptor`（frame iframe 或 tweet 特殊渲染）。无 React 依赖。

## 文件清单

| 文件                            | 职责                                                             |
| ------------------------------- | ---------------------------------------------------------------- |
| `types.ts`                      | `EmbedProvider`、`EmbedDescriptor`、`EmbedMatcher`、`bareHost()` |
| `index.ts`                      | `detectEmbed` / `isEmbeddableUrl`；MATCHERS 注册顺序             |
| `youtube.ts`                    | YouTube watch/shorts → frame embed                               |
| `vimeo.ts`                      | Vimeo → frame embed                                              |
| `instagram.ts`                  | Instagram post/reel → frame embed                                |
| `pinterest.ts`                  | Pinterest pin → frame embed                                      |
| `tiktok.ts`                     | TikTok → frame embed                                             |
| `twitter.ts`                    | X/Twitter status → tweet renderer                                |
| `spotify.ts`                    | Spotify track/album/playlist → frame embed                       |
| `maps.ts`                       | Google Maps / OpenStreetMap → frame embed                        |
| `__tests__/detectEmbed.test.ts` | `detectEmbed` / `isEmbeddableUrl` provider 矩阵回归              |

## 依赖

- 无 `@/components` / `@/store` 依赖（单向：UI → providers）

## 约束

- 每个 matcher 仅负责 host/path 判定与 descriptor 构造；不发起网络请求
- 新增 provider 须同步 `types.ts` 的 `EmbedProvider` union
