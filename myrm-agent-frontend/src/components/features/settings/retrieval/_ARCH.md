# settings/retrieval/

检索增强卡：语义搜索（嵌入模型）与重排序共用一个提供商和密钥，默认页 `sections/ai-core/DefaultModelSection.tsx` 挂载 `RetrievalCard`。

两项能力相互独立：嵌入模型只有「启用」（store 没有停用动作）；重排序是真开关，即 `useRetrievalStore.enableAdvancedRetrieval`，聊天请求（`store/chat/createMessageRequest.ts`）与 IM 渠道读取它。开关打开时若重排模型尚未生效，先校验并应用预设模型，成功后才置为开。

| 文件                        | 职责                                                                                                                              |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `RetrievalCard.tsx`         | 卡片编排：store 未加载时骨架屏；快速设置在任一模型未生效时显示；本地 `edits` 叠加在 store 之上，未改动的字段继续跟随 store        |
| `retrievalSetup.ts`         | 快速设置的业务编排（非 React）：`readQuickCredentials` 取已填提供商与密钥，`enableEmbedding`/`enableReranking`/`disableReranking` |
| `QuickSetup.tsx`            | 一个提供商 + 一个密钥；提供商限 `QUICK_SETUP_PROVIDERS`（嵌入与重排都有预设模型的那些）                                           |
| `CapabilityRows.tsx`        | `EmbeddingRow`（状态标签 + 启用按钮）与 `RerankRow`（开关）；未生效时显示将应用的预设模型                                         |
| `DisclosureNotice.tsx`      | 外发数据说明与重排序生效范围                                                                                                      |
| `AdvancedSetup.tsx`         | 折叠区：两个 `ProviderModelSelector`，用于不同提供商、自定义模型名或自托管 OpenAI 兼容端点                                        |
| `ProviderModelSelector.tsx` | Provider + 模型联动选择，应用经 `onApply` 交给调用方                                                                              |
| `ApiKeyField.tsx`           | 密钥输入（可显示/隐藏）                                                                                                           |
| `ApplyOutcome.tsx`          | 应用结果行（成功/失败文案，未应用过时不显示）                                                                                     |
| `applyMessage.ts`           | `useApplyMessage`：把 store 记录的英文校验结果映射为当前语言                                                                      |

依赖 `@/lib/search/retrievalProviders`（提供商目录与预设模型）和 `@/store/useRetrievalStore`；嵌入模型更换后的记忆迁移提示由 `memory/settings/MemoryMigrationNotice` 承担，挂在嵌入行下方。
