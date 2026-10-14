/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { wikiService, type Concept } from '@/services/wikiService';
import { useWikiConceptsList } from '../useWikiConceptsList';

const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    success: (...args: unknown[]) => toastSuccess(...args),
    info: vi.fn(),
    message: vi.fn(),
  },
}));

vi.mock('@/services/wikiService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/wikiService')>()),
  wikiService: {
    getTree: vi.fn(),
    getConcept: vi.fn(),
    applyWiki: vi.fn(),
    healConceptClaims: vi.fn(),
    deleteConcept: vi.fn(),
  },
}));

const getConceptMock = () => wikiService.getConcept as ReturnType<typeof vi.fn>;

const concept = (name: string): Concept => ({ name, content: `# ${name}` });

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useWikiConceptsList selection', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    (wikiService.getTree as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  });

  it('keeps the concept selected last when responses arrive out of order', async () => {
    const slow = deferred<Concept>();
    const fast = deferred<Concept>();
    getConceptMock().mockImplementation((id: string) => (id === 'slow' ? slow.promise : fast.promise));
    const { result } = renderHook(() => useWikiConceptsList());

    await act(async () => {
      void result.current.requestSelectConcept('slow');
      void result.current.requestSelectConcept('fast');
    });
    await act(async () => {
      fast.resolve(concept('fast'));
    });
    await act(async () => {
      slow.resolve(concept('slow'));
    });

    expect(result.current.selectedConcept?.name).toBe('fast');
  });

  it('stays silent about a failed selection that was already replaced', async () => {
    const slow = deferred<Concept>();
    getConceptMock().mockImplementation((id: string) => (id === 'slow' ? slow.promise : Promise.resolve(concept(id))));
    const { result } = renderHook(() => useWikiConceptsList());

    await act(async () => {
      void result.current.requestSelectConcept('slow');
      void result.current.requestSelectConcept('fast');
    });
    await act(async () => {
      slow.reject(new Error('network'));
    });

    expect(toastError).not.toHaveBeenCalled();
    expect(result.current.selectedConcept?.name).toBe('fast');
  });

  it('reports the failure of the latest selection', async () => {
    getConceptMock().mockRejectedValue(new Error('network'));
    const { result } = renderHook(() => useWikiConceptsList());

    await act(async () => {
      await result.current.requestSelectConcept('broken');
    });

    expect(toastError).toHaveBeenCalledTimes(1);
    expect(result.current.selectedConcept).toBeNull();
  });

  it('drops a pending selection once the agent scope changes', async () => {
    const pending = deferred<Concept>();
    getConceptMock().mockReturnValue(pending.promise);
    const { result, rerender } = renderHook(({ agentScopeId }) => useWikiConceptsList({ agentScopeId }), {
      initialProps: { agentScopeId: 'agent-a' },
    });

    await act(async () => {
      void result.current.requestSelectConcept('page');
    });
    rerender({ agentScopeId: 'agent-b' });
    await act(async () => {
      pending.resolve(concept('page'));
    });

    expect(result.current.selectedConcept).toBeNull();
  });
});

describe('useWikiConceptsList late writes after an action', () => {
  type Hook = ReturnType<typeof useWikiConceptsList>;

  const refreshedA: Concept = { name: 'A', content: '# A refreshed' };

  beforeEach(() => {
    vi.resetAllMocks();
    (wikiService.getTree as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (wikiService.applyWiki as ReturnType<typeof vi.fn>).mockResolvedValue({});
    (wikiService.healConceptClaims as ReturnType<typeof vi.fn>).mockResolvedValue({ total_healed_evidence: 0 });
  });

  // A 选中后发起操作，操作的刷新请求挂起期间改选 B；返回 B 已选中、A 的刷新尚未落地的 hook
  async function startActionThenSelectB(action: (hook: Hook) => Promise<void>) {
    const refresh = deferred<Concept>();
    let loadsOfA = 0;
    getConceptMock().mockImplementation((id: string) => {
      if (id === 'B') {
        return Promise.resolve(concept('B'));
      }
      loadsOfA += 1;
      return loadsOfA === 1 ? Promise.resolve(concept('A')) : refresh.promise;
    });
    const onVaultMutated = vi.fn();
    const { result } = renderHook(() => useWikiConceptsList({ onVaultMutated }));

    await act(async () => {
      await result.current.requestSelectConcept('A');
    });
    await act(async () => {
      void action(result.current);
    });
    await act(async () => {
      await result.current.requestSelectConcept('B');
    });
    return { result, refresh, onVaultMutated };
  }

  it.each<[string, (hook: Hook) => Promise<void>]>([
    ['heal claims', (hook) => hook.handleHealClaims()],
    ['update claim status', (hook) => hook.handleUpdateClaimStatus('claim-1', 'supported')],
    [
      'save',
      async (hook) => {
        hook.handleEdit();
        await hook.handleSave();
      },
    ],
  ])('keeps the newer selection when the refresh of %s arrives late', async (_label, action) => {
    const { result, refresh, onVaultMutated } = await startActionThenSelectB(action);

    await act(async () => {
      refresh.resolve(refreshedA);
    });

    expect(result.current.selectedConcept?.name).toBe('B');
    expect(onVaultMutated).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['reselected meanwhile', 'B', 'B'],
    ['untouched meanwhile', null, null],
  ])('after deleting the selected concept finishes late (%s)', async (_label, reselect, expected) => {
    const deletion = deferred<void>();
    (wikiService.deleteConcept as ReturnType<typeof vi.fn>).mockReturnValue(deletion.promise);
    getConceptMock().mockImplementation((id: string) => Promise.resolve(concept(id)));
    const { result } = renderHook(() => useWikiConceptsList());

    await act(async () => {
      await result.current.requestSelectConcept('A');
    });
    await act(async () => {
      result.current.handleDeleteRequest({ name: 'A', isDir: false });
    });
    await act(async () => {
      void result.current.confirmDelete();
    });
    if (reselect) {
      await act(async () => {
        await result.current.requestSelectConcept(reselect);
      });
    }
    await act(async () => {
      deletion.resolve();
    });

    expect(result.current.selectedConcept?.name ?? null).toBe(expected);
  });

  it('applies the refreshed concept when nothing else was selected meanwhile', async () => {
    getConceptMock().mockResolvedValueOnce(concept('A')).mockResolvedValueOnce(refreshedA);
    const { result } = renderHook(() => useWikiConceptsList());

    await act(async () => {
      await result.current.requestSelectConcept('A');
    });
    await act(async () => {
      await result.current.handleHealClaims();
    });

    expect(result.current.selectedConcept?.content).toBe('# A refreshed');
  });
});
