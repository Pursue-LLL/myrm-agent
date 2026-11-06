import {
  DEFAULT_PROVIDER_ID,
  EMBEDDING_PROVIDERS,
  QUICK_SETUP_PROVIDERS,
  RERANKER_PROVIDERS,
  getPresetModel,
  type ProviderConfig,
} from '@/lib/search/retrievalProviders';
import useRetrievalStore, { type ProviderModelConfig, type RetrievalConfig } from '@/store/useRetrievalStore';

/** One provider and key that set up both retrieval models. */
export interface QuickCredentials {
  providerId: string;
  apiKey: string;
}

type RetrievalSnapshot = Pick<
  RetrievalConfig,
  'embeddingConfig' | 'embeddingApplied' | 'rerankerConfig' | 'rerankerApplied'
>;

/**
 * Where the quick setup starts: the credentials of a model that is already applied, so one key serves both,
 * otherwise what was typed into the embedding config. A provider the quick setup cannot use is not carried over.
 */
export function readQuickCredentials(state: RetrievalSnapshot): QuickCredentials {
  const source = state.embeddingApplied || !state.rerankerApplied ? state.embeddingConfig : state.rerankerConfig;
  if (!QUICK_SETUP_PROVIDERS.some((provider) => provider.id === source.provider)) {
    return { providerId: DEFAULT_PROVIDER_ID, apiKey: '' };
  }
  return { providerId: source.provider, apiKey: source.apiKey };
}

function presetConfig(providers: ProviderConfig[], { providerId, apiKey }: QuickCredentials): ProviderModelConfig {
  return { provider: providerId, model: getPresetModel(providers, providerId), apiKey, apiBase: '' };
}

/** Applies the provider's preset embedding model; the outcome lands in the store's apply status and message. */
export async function enableEmbedding(credentials: QuickCredentials): Promise<void> {
  const store = useRetrievalStore.getState();
  store.setEmbeddingConfig(presetConfig(EMBEDDING_PROVIDERS, credentials));
  await store.applyEmbedding();
}

/**
 * Turns reranking on. Without an applied reranker the preset one is validated first and the switch stays off if
 * that fails; an applied reranker is never replaced by the preset.
 */
export async function enableReranking(credentials: QuickCredentials): Promise<void> {
  const store = useRetrievalStore.getState();
  if (!store.rerankerApplied) {
    store.setRerankerConfig(presetConfig(RERANKER_PROVIDERS, credentials));
    const { success } = await store.applyReranker();
    if (!success) {
      return;
    }
  }
  store.setEnableAdvancedRetrieval(true);
}

/** Switches reranking off but keeps the reranker, so turning it back on needs no key. */
export function disableReranking(): void {
  useRetrievalStore.getState().setEnableAdvancedRetrieval(false);
}
