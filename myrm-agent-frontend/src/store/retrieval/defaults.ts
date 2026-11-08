import {
  DEFAULT_PROVIDER_ID,
  EMBEDDING_PROVIDERS,
  RERANKER_PROVIDERS,
  getPresetModel,
} from '@/lib/search/retrievalProviders';
import type { RetrievalConfig } from './types';

export const DEFAULT_CONFIG: RetrievalConfig = {
  embeddingConfig: {
    provider: DEFAULT_PROVIDER_ID,
    model: getPresetModel(EMBEDDING_PROVIDERS, DEFAULT_PROVIDER_ID),
    apiKey: '',
    apiBase: '',
  },
  embeddingApplied: false,
  embeddingAppliedAt: undefined,
  embeddingApplyStatus: 'idle',
  embeddingApplyMessage: undefined,
  rerankerConfig: {
    provider: DEFAULT_PROVIDER_ID,
    model: getPresetModel(RERANKER_PROVIDERS, DEFAULT_PROVIDER_ID),
    apiKey: '',
    apiBase: '',
  },
  rerankerApplied: false,
  rerankerAppliedAt: undefined,
  rerankerApplyStatus: 'idle',
  rerankerApplyMessage: undefined,
  enableAdvancedRetrieval: false,
  orphanCount: 0,
  reindexStatus: 'idle',
  reindexProgress: { done: 0, total: 0 },
  reindexResult: null,
};
