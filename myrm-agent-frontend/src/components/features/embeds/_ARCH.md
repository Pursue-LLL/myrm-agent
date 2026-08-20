# embeds/

## 架构概述

消息/ Markdown 中的外链 URL 富媒体嵌入：按 host 匹配 provider → 用户 consent gate → lazy iframe 渲染。非 embeddable 裸链由 `MarkdownContent` 调用同目录 `OgCard`。

## 文件清单

| 文件                     | 地位   | 职责                                                                 |
| ------------------------ | ------ | -------------------------------------------------------------------- |
| `index.ts`               | 门面   | 导出 `UrlEmbed`、`detectEmbed`、`isEmbeddableUrl`、`EmbedDescriptor` |
| `UrlEmbed.tsx`           | 核心   | consent 模式（off/always/per-provider）、lazy 加载、intrinsic size   |
| `EmbedFacade.tsx`        | 辅助   | 未 consent 时的「Load {provider}」占位与 always-allow 菜单           |
| `EmbedFail.tsx`          | 辅助   | 渲染失败 fallback                                                    |
| `EmbedErrorBoundary.tsx` | 辅助   | iframe 加载错误边界                                                  |
| `FrameEmbedRenderer.tsx` | 核心   | iframe 沙箱渲染（lazy chunk）                                        |
| `OgCard.tsx`             | 辅助   | OG 元数据卡片（由 `MarkdownContent` 对非 embeddable 裸链调用）       |
| `providers/`             | 子模块 | URL → `EmbedDescriptor` 匹配器注册表                                 | [_ARCH.md](providers/_ARCH.md) |

## 依赖

- `@/store/useEmbedConsentStore` — 全局 embed 模式与 per-provider allowlist
- 消费者：`message-box/MarkdownContent.tsx`（assistant 消息 Markdown 链接渲染）

## 约束

- 新平台适配器放 `providers/<name>.ts` 并注册到 `providers/index.ts` MATCHERS
- 用户可见文案走 i18n；iframe consent UI 不含开发者注释
- 测试：单元 `providers/__tests__/detectEmbed.test.ts`；Chrome E2E 三模式 `myrm-agent-server/tests/e2e/test_link_embed_consent_chrome_e2e.py`（READ+SHPOIB，seed `POST .../seed-embed-fixture`）
