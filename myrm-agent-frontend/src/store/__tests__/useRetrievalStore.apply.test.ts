/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const manager = vi.hoisted(() => ({ set: vi.fn() }));
const estimateMock = vi.hoisted(() => vi.fn());

vi.mock('@/services/config', () => ({ getConfigSyncManager: () => manager }));
vi.mock('@/services/memory/reindex', () => ({
  getMemoryOrphanEstimate: estimateMock,
  startMemoryReindex: vi.fn(),
  getMemoryReindexStatus: vi.fn(),
}));

import useRetrievalStore from '../useRetrievalStore';

const fetchMock = vi.fn();
const reply = (body: { success?: boolean; message?: string }, ok = true) => ({ ok, json: async () => body });

const EMBEDDING = { provider: 'siliconflow', model: 'BAAI/bge-m3', apiKey: 'sk-embed', apiBase: '' };
const RERANKER = { provider: 'siliconflow', model: 'BAAI/bge-reranker-v2-m3', apiKey: 'sk-rerank', apiBase: '' };

/** The JSON body of the n-th request sent to the validation proxy. */
function requestBody(call = 0): Record<string, string | null> {
  const [, init] = fetchMock.mock.calls[call] as [string, RequestInit];
  return JSON.parse(String(init.body));
}

describe('retrieval store: applying a model', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    estimateMock.mockReset().mockResolvedValue({ total_memories: 0 });
    manager.set.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    useRetrievalStore.getState().reset();
    useRetrievalStore.setState({ embeddingConfig: EMBEDDING, rerankerConfig: RERANKER });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('embedding', () => {
    it('validates the model through the proxy, records it as applied and syncs it', async () => {
      fetchMock.mockResolvedValueOnce(reply({ success: true, message: 'Validation successful (dimension: 1024)' }));

      const result = await useRetrievalStore.getState().applyEmbedding();

      expect(result).toEqual({ success: true, message: 'Validation successful (dimension: 1024)' });
      expect(fetchMock.mock.calls[0][0]).toBe('/api/retrieval/validate/embedding');
      expect(requestBody()).toEqual({
        model: 'openai/BAAI/bge-m3',
        api_key: 'sk-embed',
        api_base: 'https://api.siliconflow.cn/v1',
        provider: 'siliconflow',
      });
      const state = useRetrievalStore.getState();
      expect(state).toMatchObject({ embeddingApplied: true, embeddingApplyStatus: 'success' });
      expect(state.embeddingAppliedAt).toEqual(expect.any(Number));
      expect(manager.set).toHaveBeenCalledWith(
        'retrieval',
        expect.objectContaining({ embeddingApplied: true, embeddingConfig: EMBEDDING, enableAdvancedRetrieval: false }),
      );
    });

    it('asks which memories the new model leaves behind', async () => {
      fetchMock.mockResolvedValueOnce(reply({ success: true, message: 'ok' }));

      await useRetrievalStore.getState().applyEmbedding();

      expect(estimateMock).toHaveBeenCalledTimes(1);
    });

    it('refuses a config without a key before sending anything', async () => {
      useRetrievalStore.setState({ embeddingConfig: { ...EMBEDDING, apiKey: '' } });

      const result = await useRetrievalStore.getState().applyEmbedding();

      expect(result).toEqual({ success: false, message: 'Missing required fields' });
      expect(fetchMock).not.toHaveBeenCalled();
      expect(manager.set).not.toHaveBeenCalled();
      expect(useRetrievalStore.getState()).toMatchObject({
        embeddingApplied: false,
        embeddingApplyStatus: 'error',
        embeddingApplyMessage: 'Missing required fields',
      });
    });

    it('reports the reason the service gives and syncs nothing', async () => {
      fetchMock.mockResolvedValueOnce(reply({ success: false, message: 'Validation failed: Invalid key' }, false));

      const result = await useRetrievalStore.getState().applyEmbedding();

      expect(result).toEqual({ success: false, message: 'Validation failed: Invalid key' });
      expect(useRetrievalStore.getState()).toMatchObject({ embeddingApplied: false, embeddingApplyStatus: 'error' });
      expect(manager.set).not.toHaveBeenCalled();
      expect(estimateMock).not.toHaveBeenCalled();
    });

    it('reports a network failure with its own message', async () => {
      fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));

      const result = await useRetrievalStore.getState().applyEmbedding();

      expect(result).toEqual({ success: false, message: 'Failed to fetch' });
      expect(useRetrievalStore.getState().embeddingApplyStatus).toBe('error');
    });

    it('keeps an earlier applied model when re-applying fails', async () => {
      useRetrievalStore.setState({ embeddingApplied: true, embeddingAppliedAt: 1 });
      fetchMock.mockResolvedValueOnce(reply({ success: false, message: 'Validation failed' }, false));

      await useRetrievalStore.getState().applyEmbedding();

      expect(useRetrievalStore.getState()).toMatchObject({ embeddingApplied: true, embeddingAppliedAt: 1 });
    });

    it.each([
      [
        'the entered address over the provider default',
        'siliconflow',
        'https://proxy.example/v1',
        'https://proxy.example/v1',
      ],
      ['the provider default when none is entered', 'siliconflow', '', 'https://api.siliconflow.cn/v1'],
      ['no address for a provider without a default', 'jina_ai', '', null],
    ])('sends %s', async (_name, provider, apiBase, expected) => {
      useRetrievalStore.setState({ embeddingConfig: { ...EMBEDDING, provider, apiBase } });
      fetchMock.mockResolvedValueOnce(reply({ success: true, message: 'ok' }));

      await useRetrievalStore.getState().applyEmbedding();

      expect(requestBody().api_base).toBe(expected);
    });
  });

  describe('reranker', () => {
    it('validates through the reranker endpoint, records it as applied and syncs it', async () => {
      fetchMock.mockResolvedValueOnce(reply({ success: true, message: 'Validation successful (returned 1 result)' }));

      const result = await useRetrievalStore.getState().applyReranker();

      expect(result.success).toBe(true);
      expect(fetchMock.mock.calls[0][0]).toBe('/api/retrieval/validate/reranker');
      expect(requestBody()).toMatchObject({ model: 'openai/BAAI/bge-reranker-v2-m3', api_key: 'sk-rerank' });
      expect(useRetrievalStore.getState()).toMatchObject({ rerankerApplied: true, rerankerApplyStatus: 'success' });
      expect(manager.set).toHaveBeenCalledWith(
        'retrieval',
        expect.objectContaining({ rerankerApplied: true, rerankerConfig: RERANKER }),
      );
    });

    it('does not look for orphaned memories: only the embedding model owns them', async () => {
      fetchMock.mockResolvedValueOnce(reply({ success: true, message: 'ok' }));

      await useRetrievalStore.getState().applyReranker();

      expect(estimateMock).not.toHaveBeenCalled();
    });

    it('refuses a config without a key before sending anything', async () => {
      useRetrievalStore.setState({ rerankerConfig: { ...RERANKER, apiKey: '' } });

      const result = await useRetrievalStore.getState().applyReranker();

      expect(result).toEqual({ success: false, message: 'Missing required fields' });
      expect(fetchMock).not.toHaveBeenCalled();
      expect(useRetrievalStore.getState().rerankerApplied).toBe(false);
    });

    it('reports the reason the service gives and syncs nothing', async () => {
      fetchMock.mockResolvedValueOnce(reply({ success: false, message: 'Validation failed: Invalid key' }, false));

      const result = await useRetrievalStore.getState().applyReranker();

      expect(result).toEqual({ success: false, message: 'Validation failed: Invalid key' });
      expect(useRetrievalStore.getState()).toMatchObject({ rerankerApplied: false, rerankerApplyStatus: 'error' });
      expect(manager.set).not.toHaveBeenCalled();
    });
  });

  describe('editing and the switch', () => {
    it('clears the apply outcome when a config is edited, without syncing it', () => {
      useRetrievalStore.setState({ embeddingApplyStatus: 'error', embeddingApplyMessage: 'Validation failed' });

      useRetrievalStore.getState().setEmbeddingConfig({ ...EMBEDDING, apiKey: 'sk-new' });

      expect(useRetrievalStore.getState()).toMatchObject({
        embeddingApplyStatus: 'idle',
        embeddingApplyMessage: undefined,
        embeddingConfig: { apiKey: 'sk-new' },
      });
      expect(manager.set).not.toHaveBeenCalled();
    });

    it('stores the switch and syncs it together with the configs', () => {
      useRetrievalStore.getState().setEnableAdvancedRetrieval(true);

      expect(useRetrievalStore.getState().enableAdvancedRetrieval).toBe(true);
      expect(manager.set).toHaveBeenCalledWith(
        'retrieval',
        expect.objectContaining({
          enableAdvancedRetrieval: true,
          embeddingConfig: EMBEDDING,
          rerankerConfig: RERANKER,
        }),
      );
    });
  });
});
