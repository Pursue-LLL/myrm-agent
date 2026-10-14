/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { wikiService, type Concept } from '@/services/wikiService';
import { useWikiConceptsList } from '../useWikiConceptsList';

const toastError = vi.fn();

vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    success: vi.fn(),
  },
}));

vi.mock('@/services/wikiService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/wikiService')>()),
  wikiService: {
    getTree: vi.fn(),
    getConcept: vi.fn(),
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
