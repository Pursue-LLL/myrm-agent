/** @vitest-environment jsdom */
// The real store, sync manager and sandbox adapter talk to a fake server that, like the real one, answers the
// orphan estimate from the retrieval config it has saved so far: the estimate is only right once the save landed.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.hoisted(() => {
  process.env.NEXT_PUBLIC_DEPLOY_MODE = 'sandbox';
});

import { resetConfigSyncManager } from '@/services/config';
import useRetrievalStore from '../useRetrievalStore';

const MEMORIES_LEFT_BEHIND = 5;
const NEW_EMBEDDING = { provider: 'siliconflow', model: 'new-model', apiKey: 'sk-embed', apiBase: '' };

type ConfigSyncOutcome = 'saved' | 'refused' | 'unreachable';
type RequestKind = 'validate' | 'config-sync' | 'estimate';

const json = (body: object, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

/** Answers the three calls an apply makes, in the order they arrive. */
function createServer(configSync: ConfigSyncOutcome): { requests: RequestKind[]; fetch: typeof fetch } {
  const requests: RequestKind[] = [];
  let savedModel = 'old-model';

  const answer = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    if (url.endsWith('/api/retrieval/validate/embedding')) {
      requests.push('validate');
      return json({ success: true, message: 'ok' });
    }
    if (url.endsWith('/config/sync')) {
      requests.push('config-sync');
      if (configSync === 'unreachable') {
        throw new TypeError('Failed to fetch');
      }
      if (configSync === 'refused') {
        return json({ detail: 'Internal Server Error' }, 500);
      }
      const body = JSON.parse(String(init?.body)) as { changes: { value: { embeddingConfig?: { model: string } } }[] };
      savedModel = body.changes[0].value.embeddingConfig?.model ?? savedModel;
      return json({ success: true, conflicts: [], newVersions: { retrieval: '1_0' } });
    }
    if (url.endsWith('/memory/reindex/estimate')) {
      requests.push('estimate');
      return json({ total_memories: savedModel === NEW_EMBEDDING.model ? MEMORIES_LEFT_BEHIND : 0 });
    }
    return json({}, 404);
  };

  return { requests, fetch: vi.fn(answer) as unknown as typeof fetch };
}

/** Lets the work an apply starts in the background run to its end. */
const settle = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 50));

async function applyNewEmbedding(configSync: ConfigSyncOutcome): Promise<RequestKind[]> {
  const server = createServer(configSync);
  vi.stubGlobal('fetch', server.fetch);
  useRetrievalStore.getState().reset();
  useRetrievalStore.setState({ embeddingConfig: NEW_EMBEDDING });

  const result = await useRetrievalStore.getState().applyEmbedding();

  expect(result.success).toBe(true);
  return server.requests;
}

describe('retrieval store: the orphan estimate after applying an embedding model', () => {
  beforeEach(() => {
    resetConfigSyncManager();
    localStorage.setItem('auth_token', 'test-token');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    resetConfigSyncManager();
  });

  it('asks only after the new model is saved, so the notice counts the memories it leaves behind', async () => {
    const requests = await applyNewEmbedding('saved');

    await vi.waitFor(() => expect(useRetrievalStore.getState().orphanCount).toBe(MEMORIES_LEFT_BEHIND));
    expect(requests).toEqual(['validate', 'config-sync', 'estimate']);
  });

  it('does not ask when the server refuses the save, and the apply stays successful', async () => {
    const requests = await applyNewEmbedding('refused');
    await settle();

    expect(requests).toEqual(['validate', 'config-sync']);
    expect(useRetrievalStore.getState()).toMatchObject({ embeddingApplyStatus: 'success', orphanCount: 0 });
  });

  it('does not ask when the save could not be sent, and the apply stays successful', async () => {
    const requests = await applyNewEmbedding('unreachable');
    await settle();

    expect(requests).toEqual(['validate', 'config-sync']);
    expect(useRetrievalStore.getState()).toMatchObject({ embeddingApplyStatus: 'success', orphanCount: 0 });
  });
});
