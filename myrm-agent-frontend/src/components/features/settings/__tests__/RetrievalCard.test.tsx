import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const manager = vi.hoisted(() => ({ set: vi.fn() }));

vi.mock('@/services/config', () => ({ getConfigSyncManager: () => manager }));
vi.mock('@/services/memory/reindex', () => ({
  getMemoryOrphanEstimate: vi.fn().mockResolvedValue({ total_memories: 0 }),
  startMemoryReindex: vi.fn(),
  getMemoryReindexStatus: vi.fn(),
}));
vi.mock('@/components/features/memory/settings/MemoryMigrationNotice', () => ({
  default: () => <div data-testid="migration-notice" />,
}));

import type { RetrievalConfig } from '@/store/retrieval/types';
import useRetrievalStore from '@/store/useRetrievalStore';

import RetrievalCard from '../retrieval/RetrievalCard';

const fetchMock = vi.fn();
const reply = (body: { success?: boolean; message?: string }, ok = true) => ({ ok, json: async () => body });
const EMBEDDING_OK = reply({ success: true, message: 'Validation successful (dimension: 1024)' });
const RERANKER_OK = reply({ success: true, message: 'Validation successful (returned 2 results)' });

/** The JSON body of the n-th request sent to the validation proxy. */
function requestBody(call = 0): Record<string, string | null> {
  const [, init] = fetchMock.mock.calls[call] as [string, RequestInit];
  return JSON.parse(String(init.body));
}

/** Makes the next validation request hang until the test lets it finish. */
function deferredReply() {
  const pending: { finish: (response: ReturnType<typeof reply>) => void } = { finish: () => {} };
  fetchMock.mockReturnValue(new Promise((resolve) => (pending.finish = resolve)));
  return pending;
}

const requestedUrls = () => fetchMock.mock.calls.map(([url]) => url as string);
const applied = (provider: string, model: string, apiKey: string) => ({ provider, model, apiKey, apiBase: '' });

const typeKey = (apiKey: string) => fireEvent.change(screen.getByLabelText('apiKey'), { target: { value: apiKey } });
const rerankSwitch = () => screen.getByRole('switch', { name: 'rerank.title' });
const enableButton = () => screen.getByRole('button', { name: 'embedding.enable' });

function mountLoaded(state: Partial<RetrievalConfig> = {}) {
  useRetrievalStore.setState({ isInitialized: true, ...state });
  return render(<RetrievalCard />);
}

describe('RetrievalCard', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    manager.set.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    useRetrievalStore.getState().reset();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    useRetrievalStore.setState({ isInitialized: false });
  });

  it('shows a skeleton instead of controls until the store has loaded', () => {
    useRetrievalStore.setState({ isInitialized: false });
    render(<RetrievalCard />);

    expect(screen.getByText('card.title')).toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'embedding.enable' })).not.toBeInTheDocument();
  });

  it('offers one provider and key with the preset models while nothing is enabled', () => {
    mountLoaded();

    expect(screen.getByText('Silicon Flow（硅基流动）')).toBeInTheDocument();
    expect(screen.getByLabelText('apiKey')).toHaveValue('');
    expect(screen.getByText('embedding.notEnabled')).toBeInTheDocument();
    expect(screen.getByText('BAAI/bge-m3')).toBeInTheDocument();
    expect(screen.getByText('BAAI/bge-reranker-v2-m3')).toBeInTheDocument();
    expect(rerankSwitch()).toHaveAttribute('aria-checked', 'false');
  });

  it('enables semantic search with the typed key and the provider preset', async () => {
    fetchMock.mockResolvedValue(EMBEDDING_OK);
    mountLoaded();

    typeKey('sk-typed');
    fireEvent.click(enableButton());

    await waitFor(() => expect(screen.getByText('embedding.enabled')).toBeInTheDocument());
    expect(requestedUrls()).toEqual(['/api/retrieval/validate/embedding']);
    expect(requestBody()).toMatchObject({ model: 'openai/BAAI/bge-m3', api_key: 'sk-typed', provider: 'siliconflow' });
    expect(screen.getByText('validationMessages.successWithDimension')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'embedding.enable' })).not.toBeInTheDocument();
    expect(rerankSwitch()).toHaveAttribute('aria-checked', 'false');
  });

  it('turns reranking on by setting the reranker up first', async () => {
    fetchMock.mockResolvedValue(RERANKER_OK);
    mountLoaded();

    typeKey('sk-typed');
    fireEvent.click(rerankSwitch());

    await waitFor(() => expect(rerankSwitch()).toHaveAttribute('aria-checked', 'true'));
    expect(requestedUrls()).toEqual(['/api/retrieval/validate/reranker']);
    expect(requestBody()).toMatchObject({ api_key: 'sk-typed', provider: 'siliconflow' });
    expect(useRetrievalStore.getState()).toMatchObject({ rerankerApplied: true, enableAdvancedRetrieval: true });
    expect(screen.getByText('validationMessages.successWithResults')).toBeInTheDocument();
    expect(screen.getByText('embedding.notEnabled')).toBeInTheDocument();
  });

  it('keeps the switch off and shows the reason when the reranker is rejected', async () => {
    fetchMock.mockResolvedValue(reply({ success: false, message: 'Validation failed: Invalid API key' }, false));
    mountLoaded();

    typeKey('bad-key');
    fireEvent.click(rerankSwitch());

    await waitFor(() => expect(screen.getByText('validationMessages.failedWithError')).toBeInTheDocument());
    expect(rerankSwitch()).toHaveAttribute('aria-checked', 'false');
    expect(useRetrievalStore.getState().enableAdvancedRetrieval).toBe(false);
  });

  it('asks for a key instead of calling the provider when none was typed', async () => {
    mountLoaded();

    fireEvent.click(enableButton());

    await waitFor(() => expect(screen.getByText('validationMessages.missingRequiredFields')).toBeInTheDocument());
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('locks the rerank switch, and only it, while its request is in flight', async () => {
    const pending = deferredReply();
    mountLoaded();

    typeKey('sk-typed');
    fireEvent.click(rerankSwitch());

    await waitFor(() => expect(rerankSwitch()).toBeDisabled());
    expect(enableButton()).toBeEnabled();

    pending.finish(RERANKER_OK);
    await waitFor(() => expect(rerankSwitch()).toBeEnabled());
  });

  it('locks the enable button, and only it, while its request is in flight', async () => {
    const pending = deferredReply();
    mountLoaded();

    typeKey('sk-typed');
    fireEvent.click(enableButton());

    await waitFor(() => expect(enableButton()).toBeDisabled());
    expect(rerankSwitch()).toBeEnabled();

    pending.finish(EMBEDDING_OK);
    await waitFor(() => expect(screen.getByText('embedding.enabled')).toBeInTheDocument());
  });

  it('reuses the applied embedding provider and key when reranking is switched on', async () => {
    fetchMock.mockResolvedValue(RERANKER_OK);
    mountLoaded({ embeddingConfig: applied('jina_ai', 'jina-embeddings-v3', 'jina-key'), embeddingApplied: true });

    expect(screen.getByLabelText('apiKey')).toHaveValue('jina-key');
    expect(screen.getByText('embedding.enabled')).toBeInTheDocument();

    fireEvent.click(rerankSwitch());

    await waitFor(() => expect(rerankSwitch()).toHaveAttribute('aria-checked', 'true'));
    expect(requestBody()).toMatchObject({
      model: 'jina_ai/jina-reranker-v2-base-multilingual',
      api_key: 'jina-key',
      provider: 'jina_ai',
    });
  });

  it('follows the provider picked in the quick setup for presets and requests', async () => {
    fetchMock.mockResolvedValue(EMBEDDING_OK);
    mountLoaded();

    fireEvent.click(screen.getByText('Silicon Flow（硅基流动）'));
    fireEvent.click(screen.getByText('Cohere'));

    expect(screen.getByText('embed-multilingual-v3.0')).toBeInTheDocument();
    expect(screen.getByText('rerank-v3.5')).toBeInTheDocument();

    typeKey('cohere-key');
    fireEvent.click(enableButton());

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(requestBody()).toMatchObject({
      model: 'cohere/embed-multilingual-v3.0',
      api_key: 'cohere-key',
      provider: 'cohere',
    });
  });

  it('hides the quick setup once both models are applied and toggles reranking without a request', () => {
    mountLoaded({
      embeddingConfig: applied('jina_ai', 'jina-embeddings-v3', 'k'),
      embeddingApplied: true,
      rerankerConfig: applied('jina_ai', 'jina-reranker-v2-base-multilingual', 'k'),
      rerankerApplied: true,
      enableAdvancedRetrieval: true,
    });

    expect(screen.queryByLabelText('apiKey')).not.toBeInTheDocument();
    expect(screen.queryByText('jina-reranker-v2-base-multilingual')).not.toBeInTheDocument();
    expect(rerankSwitch()).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(rerankSwitch());
    expect(rerankSwitch()).toHaveAttribute('aria-checked', 'false');
    expect(useRetrievalStore.getState().rerankerApplied).toBe(true);

    fireEvent.click(rerankSwitch());
    expect(rerankSwitch()).toHaveAttribute('aria-checked', 'true');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('shows the switch off when the flag is on but the reranker is not set up', () => {
    mountLoaded({ enableAdvancedRetrieval: true, rerankerApplied: false });

    expect(rerankSwitch()).toHaveAttribute('aria-checked', 'false');
  });

  it('reveals and hides the typed key on request', () => {
    mountLoaded();

    expect(screen.getByLabelText('apiKey')).toHaveAttribute('type', 'password');
    fireEvent.click(screen.getByRole('button', { name: 'showApiKey' }));
    expect(screen.getByLabelText('apiKey')).toHaveAttribute('type', 'text');
    fireEvent.click(screen.getByRole('button', { name: 'hideApiKey' }));
    expect(screen.getByLabelText('apiKey')).toHaveAttribute('type', 'password');
  });

  it('states what is sent to the provider and where reranking applies', () => {
    mountLoaded();

    for (const key of ['title', 'embedding', 'rerank', 'pageReading', 'coverage']) {
      expect(screen.getByText(`disclosure.${key}`)).toBeInTheDocument();
    }
  });

  it('keeps the per-model configuration collapsed until it is opened', () => {
    mountLoaded();

    expect(screen.queryByText('hint.options')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'apply.button' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'advanced.title' }));

    expect(screen.getByText('hint.options')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'apply.button' })).toHaveLength(2);
  });

  it('shows the migration notice under the semantic-search row', () => {
    mountLoaded();

    expect(screen.getByTestId('migration-notice')).toBeInTheDocument();
  });
});
