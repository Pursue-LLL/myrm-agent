# lib/search/ 模块架构

## 架构概述

检索相关纯逻辑：SearXNG 区域预设（与 harness 对齐）及 Settings 中 Embedding/Reranker provider 目录（含各提供商的预设模型）。

## 文件清单

| 文件                                   | 地位 | 职责                                                                                                                        |
| -------------------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------- |
| `searxngPresets.ts`                    | 核心 | SearXNG region preset 常量与 detect/build 辅助函数                                                                          |
| `retrievalProviders.ts`                | 核心 | Embedding/Reranker provider 目录（每家首个模型即预设）、`QUICK_SETUP_PROVIDERS` 与 `toRoutedModelId`（Settings Apply 路径） |
| `__tests__/retrievalProviders.test.ts` | 测试 | 预设模型取值、快速设置提供商集合、`toRoutedModelId` 单元测试                                                                |
| `__tests__/searxngPresets.test.ts`     | 测试 | preset detect/build 单元测试                                                                                                |

## 依赖

- `searxngPresets.ts` 的消费方：`SearchServiceEditDialog.tsx`、`store/config/quickSearchSetup.ts`
- `retrievalProviders.ts` 的消费方：`useRetrievalStore.ts`、`store/retrieval/defaults.ts` 与 `settings/retrieval/` 下的 `RetrievalCard.tsx`、`QuickSetup.tsx`、`AdvancedSetup.tsx`、`ProviderModelSelector.tsx`、`retrievalSetup.ts`
- Server 侧 SearXNG 静态配置：`myrm-agent-server/searxng/_ARCH.md`

## 约束

- 无 React 组件；Settings UI 在 `components/features/settings/`。
- Provider 列表为前端静态目录，运行时密钥与模型选择仍经 WebUI Settings → server inject。
