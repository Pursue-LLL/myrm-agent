/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const manager = vi.hoisted(() => ({ set: vi.fn() }));

vi.mock('@/services/config', () => ({ getConfigSyncManager: () => manager }));
vi.mock('@/services/memory/reindex', () => ({
  getMemoryOrphanEstimate: vi.fn().mockResolvedValue({ total_memories: 0 }),
  startMemoryReindex: vi.fn(),
  getMemoryReindexStatus: vi.fn(),
}));

import useRetrievalStore from '@/store/useRetrievalStore';
import { disableReranking, enableEmbedding, enableReranking, readQuickCredentials } from '../retrieval/retrievalSetup';

const fetchMock = vi.fn();
const reply = (body: { success?: boolean; message?: string }, ok = true) => ({ ok, json: async () => body });

const JINA = { providerId: 'jina_ai', apiKey: 'jina-key' };

/** The JSON body of the n-th request sent to the validation proxy. */
function requestBody(call = 0): Record<string, string | null> {
  const [, init] = fetchMock.mock.calls[call] as [string, RequestInit];
  return JSON.parse(String(init.body));
}

const applied = (provider: string, model: string, apiKey: string) => ({ provider, model, apiKey, apiBase: '' });

describe('retrieval quick setup', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    manager.set.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    useRetrievalStore.getState().reset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('readQuickCredentials', () => {
    it('starts on the default provider without a key', () => {
      expect(readQuickCredentials(useRetrievalStore.getState())).toEqual({ providerId: 'siliconflow', apiKey: '' });
    });

    it('takes what was typed into the embedding config when nothing is applied yet', () => {
      useRetrievalStore.setState({ embeddingConfig: applied('voyage', 'voyage-3', 'typed-key') });

      expect(readQuickCredentials(useRetrievalStore.getState())).toEqual({
        providerId: 'voyage',
        apiKey: 'typed-key',
      });
    });

    it('prefers the applied embedding, so one key serves both models', () => {
      useRetrievalStore.setState({
        embeddingConfig: applied('jina_ai', 'jina-embeddings-v3', 'embed-key'),
        embeddingApplied: true,
        rerankerConfig: applied('cohere', 'rerank-v3.5', 'rerank-key'),
        rerankerApplied: true,
      });

      expect(readQuickCredentials(useRetrievalStore.getState())).toEqual({
        providerId: 'jina_ai',
        apiKey: 'embed-key',
      });
    });

    it('falls back to the applied reranker when only that one is set up', () => {
      useRetrievalStore.setState({
        rerankerConfig: applied('cohere', 'rerank-v3.5', 'rerank-key'),
        rerankerApplied: true,
      });

      expect(readQuickCredentials(useRetrievalStore.getState())).toEqual({
        providerId: 'cohere',
        apiKey: 'rerank-key',
      });
    });

    it('does not offer a provider the quick setup cannot use, nor carry its key over', () => {
      useRetrievalStore.setState({
        embeddingConfig: applied('openai', 'text-embedding-3-small', 'openai-key'),
        embeddingApplied: true,
      });

      expect(readQuickCredentials(useRetrievalStore.getState())).toEqual({ providerId: 'siliconflow', apiKey: '' });
    });
  });

  describe('enableEmbedding', () => {
    it('applies the provider’s preset embedding model with the entered key', async () => {
      fetchMock.mockResolvedValueOnce(reply({ success: true, message: 'Validation successful (dimension: 1024)' }));

      await enableEmbedding(JINA);

      expect(fetchMock.mock.calls[0][0]).toBe('/api/retrieval/validate/embedding');
      expect(requestBody()).toMatchObject({
        model: 'jina_ai/jina-embeddings-v3',
        api_key: 'jina-key',
        api_base: null,
        provider: 'jina_ai',
      });
      expect(useRetrievalStore.getState()).toMatchObject({
        embeddingConfig: applied('jina_ai', 'jina-embeddings-v3', 'jina-key'),
        embeddingApplied: true,
        embeddingApplyStatus: 'success',
      });
    });

    it('leaves the reranker alone', async () => {
      const before = useRetrievalStore.getState().rerankerConfig;
      fetchMock.mockResolvedValueOnce(reply({ success: true, message: 'ok' }));

      await enableEmbedding(JINA);

      expect(useRetrievalStore.getState().rerankerConfig).toBe(before);
      expect(useRetrievalStore.getState().rerankerApplied).toBe(false);
    });

    it('reports a rejected key and leaves the model unapplied', async () => {
      fetchMock.mockResolvedValueOnce(reply({ success: false, message: 'Validation failed: Invalid key' }, false));

      await enableEmbedding(JINA);

      expect(useRetrievalStore.getState()).toMatchObject({
        embeddingApplied: false,
        embeddingApplyStatus: 'error',
        embeddingApplyMessage: 'Validation failed: Invalid key',
      });
    });

    it('asks for a key instead of sending an empty one', async () => {
      await enableEmbedding({ providerId: 'jina_ai', apiKey: '' });

      expect(fetchMock).not.toHaveBeenCalled();
      expect(useRetrievalStore.getState()).toMatchObject({
        embeddingApplied: false,
        embeddingApplyMessage: 'Missing required fields',
      });
    });
  });

  describe('enableReranking', () => {
    it('applies the preset reranker, then turns the switch on', async () => {
      fetchMock.mockResolvedValueOnce(reply({ success: true, message: 'Validation successful (returned 1 result)' }));

      await enableReranking(JINA);

      expect(fetchMock.mock.calls[0][0]).toBe('/api/retrieval/validate/reranker');
      expect(requestBody()).toMatchObject({ model: 'jina_ai/jina-reranker-v2-base-multilingual', api_key: 'jina-key' });
      expect(useRetrievalStore.getState()).toMatchObject({
        rerankerConfig: applied('jina_ai', 'jina-reranker-v2-base-multilingual', 'jina-key'),
        rerankerApplied: true,
        enableAdvancedRetrieval: true,
      });
      expect(manager.set).toHaveBeenLastCalledWith(
        'retrieval',
        expect.objectContaining({ rerankerApplied: true, enableAdvancedRetrieval: true }),
      );
    });

    it('only flips the switch when a reranker is already applied, keeping that model', async () => {
      const custom = applied('cohere', 'rerank-multilingual-v3.0', 'cohere-key');
      useRetrievalStore.setState({ rerankerConfig: custom, rerankerApplied: true });

      await enableReranking(JINA);

      expect(fetchMock).not.toHaveBeenCalled();
      expect(useRetrievalStore.getState()).toMatchObject({ rerankerConfig: custom, enableAdvancedRetrieval: true });
    });

    it('keeps the switch off when the reranker is rejected', async () => {
      fetchMock.mockResolvedValueOnce(reply({ success: false, message: 'Validation failed: Invalid key' }, false));

      await enableReranking(JINA);

      expect(useRetrievalStore.getState()).toMatchObject({
        rerankerApplied: false,
        rerankerApplyMessage: 'Validation failed: Invalid key',
        enableAdvancedRetrieval: false,
      });
      expect(manager.set).not.toHaveBeenCalled();
    });

    it('asks for a key instead of switching on a reranker that is not set up', async () => {
      await enableReranking({ providerId: 'jina_ai', apiKey: '' });

      expect(fetchMock).not.toHaveBeenCalled();
      expect(useRetrievalStore.getState()).toMatchObject({
        rerankerApplyMessage: 'Missing required fields',
        enableAdvancedRetrieval: false,
      });
    });

    it('leaves the embedding alone', async () => {
      const before = useRetrievalStore.getState().embeddingConfig;
      fetchMock.mockResolvedValueOnce(reply({ success: true, message: 'ok' }));

      await enableReranking(JINA);

      expect(useRetrievalStore.getState().embeddingConfig).toBe(before);
      expect(useRetrievalStore.getState().embeddingApplied).toBe(false);
    });
  });

  describe('disableReranking', () => {
    it('turns the switch off and keeps the reranker for the next time', () => {
      const custom = applied('cohere', 'rerank-v3.5', 'cohere-key');
      useRetrievalStore.setState({ rerankerConfig: custom, rerankerApplied: true, enableAdvancedRetrieval: true });

      disableReranking();

      expect(useRetrievalStore.getState()).toMatchObject({
        rerankerConfig: custom,
        rerankerApplied: true,
        enableAdvancedRetrieval: false,
      });
      expect(manager.set).toHaveBeenLastCalledWith(
        'retrieval',
        expect.objectContaining({ enableAdvancedRetrieval: false }),
      );
      expect(fetchMock).not.toHaveBeenCalled();
    });
  });
});
