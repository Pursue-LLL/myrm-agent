/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';
import { listAgents, resetKit, router, setQuery, world } from './wikiSectionTestKit';
import { useWikiScope } from '../useWikiScope';

const AGENTS = {
  items: [
    { id: 'a1', name: 'Alpha' },
    { id: 'a2', name: 'Beta' },
  ],
};

async function setup(query = '') {
  setQuery(query);
  const rendered = renderHook(() => useWikiScope());
  await settle();
  return rendered;
}

beforeEach(() => {
  resetKit();
  listAgents.mockResolvedValue(AGENTS);
});

afterEach(cleanup);

describe('useWikiScope: the agent list', () => {
  it('reports the load from the very first render, before the list is requested', () => {
    listAgents.mockReturnValue(deferred<typeof AGENTS>().promise);
    setQuery('');
    const loadingByRender: boolean[] = [];
    renderHook(() => {
      const scope = useWikiScope();
      loadingByRender.push(scope.agentsLoading);
      return scope;
    });
    expect(loadingByRender[0]).toBe(true);
  });

  it('loads the first hundred agents once and stops reporting a load', async () => {
    const pending = deferred<typeof AGENTS>();
    listAgents.mockReturnValue(pending.promise);
    setQuery('');
    const { result } = renderHook(() => useWikiScope());
    expect(result.current.agentsLoading).toBe(true);
    expect(result.current.agents).toEqual([]);

    pending.resolve(AGENTS);
    await settle();
    expect(result.current.agentsLoading).toBe(false);
    expect(result.current.agents).toEqual(AGENTS.items);
    expect(listAgents).toHaveBeenCalledExactlyOnceWith(1, 100);
  });

  it('falls back to an empty list when the agents cannot be loaded', async () => {
    listAgents.mockRejectedValue(new Error('offline'));
    const { result } = await setup();
    expect(result.current.agents).toEqual([]);
    expect(result.current.agentsLoading).toBe(false);
  });

  it('does not reload the list when the scope changes', async () => {
    const { result } = await setup('agentId=a1');
    setQuery('agentId=a2');
    expect(result.current.agentScopeId).toBe('a2');
    expect(listAgents).toHaveBeenCalledOnce();
  });
});

describe('useWikiScope: which wiki is open', () => {
  it('is the default wiki when the URL names no agent', async () => {
    const { result } = await setup();
    expect(result.current.agentScopeId).toBeNull();
    expect(result.current.evidenceContextKey).toBe('agent:default');
    expect(result.current.scopeLabel).toBe('agentScopeDefault');
  });

  it('is the wiki of the agent the URL names', async () => {
    const { result } = await setup('agentId=a1');
    expect(result.current.agentScopeId).toBe('a1');
    expect(result.current.evidenceContextKey).toBe('agent:a1');
  });

  it('labels the scope with the agent name in the language of the interface', async () => {
    world.locale = 'ja';
    const { result } = await setup('agentId=a2');
    expect(result.current.scopeLabel).toBe('a2:Beta:ja');
  });

  it('labels an agent that is not in the list by its id', async () => {
    const { result } = await setup('agentId=ghost');
    expect(result.current.scopeLabel).toBe('ghost:ghost:en');
  });

  it('picks up the agent name once the list arrives', async () => {
    const pending = deferred<typeof AGENTS>();
    listAgents.mockReturnValue(pending.promise);
    setQuery('agentId=a1');
    const { result } = renderHook(() => useWikiScope());
    expect(result.current.scopeLabel).toBe('a1:a1:en');
    pending.resolve(AGENTS);
    await settle();
    expect(result.current.scopeLabel).toBe('a1:Alpha:en');
  });
});

describe('useWikiScope: scope revision', () => {
  it('counts one revision for the first scope and one more for every change of scope', async () => {
    const { result } = await setup();
    expect(result.current.scopeRevision).toBe(1);
    setQuery('agentId=a1');
    expect(result.current.scopeRevision).toBe(2);
    setQuery('agentId=a2');
    expect(result.current.scopeRevision).toBe(3);
    setQuery('');
    expect(result.current.scopeRevision).toBe(4);
  });

  it('keeps the revision when only another query parameter changes', async () => {
    const { result } = await setup('agentId=a1');
    setQuery('agentId=a1&wikiTab=queue');
    expect(result.current.scopeRevision).toBe(1);
  });
});

describe('useWikiScope: moving between wikis', () => {
  it('opens the agent graph tab of the library, scoped to the agent', async () => {
    const { result } = await setup('agentId=a1');
    act(() => result.current.goToKnowledgeGraph());
    expect(router.push).toHaveBeenCalledExactlyOnceWith('/library?tab=graph&agentId=a1');
  });

  it('opens the library graph without a scope for the default wiki', async () => {
    const { result } = await setup();
    act(() => result.current.goToKnowledgeGraph());
    expect(router.push).toHaveBeenCalledExactlyOnceWith('/library?tab=graph');
  });

  it('opens the graph of the agent the URL names now, not the one it named before', async () => {
    const { result } = await setup('agentId=a1');
    setQuery('agentId=a2');
    act(() => result.current.goToKnowledgeGraph());
    expect(router.push).toHaveBeenCalledExactlyOnceWith('/library?tab=graph&agentId=a2');
  });

  it('switches to another agent and keeps the rest of the query', async () => {
    const { result } = await setup('agentId=a1&wikiTab=queue');
    act(() => result.current.handleAgentScopeChange('a2'));
    expect(router.replace).toHaveBeenCalledExactlyOnceWith('/settings/wiki?agentId=a2&wikiTab=queue');
  });

  it('switches from the default wiki to an agent', async () => {
    const { result } = await setup();
    act(() => result.current.handleAgentScopeChange('a1'));
    expect(router.replace).toHaveBeenCalledExactlyOnceWith('/settings/wiki?agentId=a1');
  });

  it('goes back to the default wiki by dropping the agent from the query', async () => {
    const { result } = await setup('agentId=a1&wikiTab=queue');
    act(() => result.current.handleAgentScopeChange('default'));
    expect(router.replace).toHaveBeenCalledExactlyOnceWith('/settings/wiki?wikiTab=queue');
  });

  it('writes the bare path when the default wiki is all that is left', async () => {
    const { result } = await setup('agentId=a1');
    act(() => result.current.handleAgentScopeChange('default'));
    expect(router.replace).toHaveBeenCalledExactlyOnceWith('/settings/wiki');
  });
});
