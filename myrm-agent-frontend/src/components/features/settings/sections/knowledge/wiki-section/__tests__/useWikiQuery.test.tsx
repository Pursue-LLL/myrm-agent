/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';
import type { WikiQueryResponse } from '@/services/wikiService';
import { metrics, resetKit, service, toast } from './wikiSectionTestKit';
import { queryResponseOf, snippetOf } from './wikiSectionFixtures';
import { useWikiQuery } from '../useWikiQuery';

let consoleError: ReturnType<typeof vi.spyOn>;

function setup(scope: string | null = null, contextKey = 'agent:default') {
  return renderHook(({ scopeId, key }) => useWikiQuery(scopeId, key), {
    initialProps: { scopeId: scope, key: contextKey },
  });
}

type Rendered = ReturnType<typeof setup>;

const ask = async (rendered: Rendered, question: string) => {
  act(() => rendered.result.current.setQuery(question));
  await act(() => rendered.result.current.handleQuery());
};

beforeEach(() => {
  resetKit();
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  consoleError.mockRestore();
});

describe('useWikiQuery: starting a question', () => {
  it('opens on an empty question in automatic mode with a closed evidence drawer', () => {
    const { result } = setup();
    expect(result.current.query).toBe('');
    expect(result.current.queryMode).toBe('auto');
    expect(result.current.isQuerying).toBe(false);
    expect(result.current.answer).toBe('');
    expect(result.current.snippetDrawerState).toEqual({ open: false, title: '', snippet: '' });
  });

  it.each(['', '   ', '\n\t'])('refuses the blank question %j without asking the wiki', async (blank) => {
    const rendered = setup();
    await ask(rendered, blank);
    expect(toast.error).toHaveBeenCalledExactlyOnceWith('errors.emptyQuery');
    expect(service.queryWiki).not.toHaveBeenCalled();
    expect(metrics.attempt).not.toHaveBeenCalled();
    expect(rendered.result.current.isQuerying).toBe(false);
  });

  it('asks the wiki of the scope in the chosen mode with the question as typed', async () => {
    const rendered = setup('a1', 'agent:a1');
    act(() => rendered.result.current.setQueryMode('raw_claim'));
    await ask(rendered, '  what is x?  ');
    expect(service.queryWiki).toHaveBeenCalledExactlyOnceWith('  what is x?  ', 'raw_claim', 'a1');
  });

  it('asks the default wiki when no agent is selected', async () => {
    const rendered = setup();
    await ask(rendered, 'q');
    expect(service.queryWiki).toHaveBeenCalledExactlyOnceWith('q', 'auto', null);
  });

  it('counts the attempt for the evidence funnel before the answer arrives', async () => {
    const pending = deferred<WikiQueryResponse>();
    service.queryWiki.mockReturnValue(pending.promise);
    const rendered = setup('a1', 'agent:a1');
    act(() => rendered.result.current.setQuery('q'));
    let asking: Promise<void> = Promise.resolve();
    act(() => {
      asking = rendered.result.current.handleQuery();
    });
    expect(metrics.attempt).toHaveBeenCalledExactlyOnceWith('settings', 'agent:a1');
    expect(metrics.submitted).not.toHaveBeenCalled();
    expect(rendered.result.current.isQuerying).toBe(true);
    pending.resolve(queryResponseOf());
    await act(() => asking);
    expect(rendered.result.current.isQuerying).toBe(false);
  });

  it('clears the previous answer as soon as the next question is sent', async () => {
    const rendered = setup();
    service.queryWiki.mockResolvedValueOnce(
      queryResponseOf({
        answer: 'first',
        related_articles: ['a'],
        source_snippets: [snippetOf()],
        confidence_score: 0.9,
        refused: true,
        retrieval_trace: { index_hits: [], seeds: [], sidecar_directories: [], selected_concepts: ['c'] },
      }),
    );
    await ask(rendered, 'one');
    const pending = deferred<WikiQueryResponse>();
    service.queryWiki.mockReturnValue(pending.promise);
    let asking: Promise<void> = Promise.resolve();
    act(() => {
      asking = rendered.result.current.handleQuery();
    });
    const { answer, relatedArticles, sourceSnippets, queryConfidence, queryRefused, retrievalTrace } =
      rendered.result.current;
    expect({ answer, relatedArticles, sourceSnippets, queryConfidence, queryRefused, retrievalTrace }).toEqual({
      answer: '',
      relatedArticles: [],
      sourceSnippets: [],
      queryConfidence: null,
      queryRefused: false,
      retrievalTrace: null,
    });
    pending.resolve(queryResponseOf());
    await act(() => asking);
  });
});

describe('useWikiQuery: the answer', () => {
  it('shows the answer with its related articles, sources, confidence and retrieval trace', async () => {
    const trace = {
      index_hits: [{ link_name: 'a', summary: 'sum', score: 0.4 }],
      seeds: [],
      sidecar_directories: [],
      selected_concepts: ['a'],
    };
    service.queryWiki.mockResolvedValue(
      queryResponseOf({
        answer: 'Because of x',
        related_articles: ['concepts/a.md'],
        source_snippets: [snippetOf(), snippetOf({ path: 'concepts/b.md' })],
        confidence_score: 0.82,
        refused: false,
        retrieval_trace: trace,
      }),
    );
    const rendered = setup('a1', 'agent:a1');
    await ask(rendered, 'why');
    const state = rendered.result.current;
    expect(state.answer).toBe('Because of x');
    expect(state.relatedArticles).toEqual(['concepts/a.md']);
    expect(state.sourceSnippets).toHaveLength(2);
    expect(state.queryConfidence).toBe(0.82);
    expect(state.queryRefused).toBe(false);
    expect(state.retrievalTrace).toEqual(trace);
    expect(metrics.submitted).toHaveBeenCalledExactlyOnceWith('settings', 'agent:a1');
    expect(metrics.surface).toHaveBeenCalledExactlyOnceWith('settings', 2, 'agent:a1');
    expect(toast.success).toHaveBeenCalledExactlyOnceWith('success.queryComplete');
  });

  it('keeps a zero confidence instead of treating it as missing', async () => {
    service.queryWiki.mockResolvedValue(queryResponseOf({ confidence_score: 0 }));
    const rendered = setup();
    await ask(rendered, 'q');
    expect(rendered.result.current.queryConfidence).toBe(0);
  });

  it('marks an answer the server refused to stand behind', async () => {
    service.queryWiki.mockResolvedValue(queryResponseOf({ refused: true }));
    const rendered = setup();
    await ask(rendered, 'q');
    expect(rendered.result.current.queryRefused).toBe(true);
  });

  it('copes with a minimal response that has no articles, sources, confidence, refusal or trace', async () => {
    service.queryWiki.mockResolvedValue({ answer: 'bare' });
    const rendered = setup();
    await ask(rendered, 'q');
    const state = rendered.result.current;
    expect(state.answer).toBe('bare');
    expect(state.relatedArticles).toEqual([]);
    expect(state.sourceSnippets).toEqual([]);
    expect(state.queryConfidence).toBeNull();
    expect(state.queryRefused).toBe(false);
    expect(state.retrievalTrace).toBeNull();
    expect(metrics.surface).toHaveBeenCalledExactlyOnceWith('settings', 0, 'agent:default');
  });

  it('forgets the answer, its articles and its sources when the scope changes', async () => {
    service.queryWiki.mockResolvedValue(
      queryResponseOf({ answer: 'first', related_articles: ['a'], source_snippets: [snippetOf()] }),
    );
    const rendered = setup('a1', 'agent:a1');
    await ask(rendered, 'q');
    rendered.rerender({ scopeId: 'a2', key: 'agent:a2' });
    await settle();
    expect(rendered.result.current.answer).toBe('');
    expect(rendered.result.current.relatedArticles).toEqual([]);
    expect(rendered.result.current.sourceSnippets).toEqual([]);
    expect(rendered.result.current.query).toBe('q');
  });

  it('keeps the answer while the scope stays the same', async () => {
    service.queryWiki.mockResolvedValue(queryResponseOf({ answer: 'first' }));
    const rendered = setup('a1', 'agent:a1');
    await ask(rendered, 'q');
    rendered.rerender({ scopeId: 'a1', key: 'agent:a1' });
    await settle();
    expect(rendered.result.current.answer).toBe('first');
  });
});

describe('useWikiQuery: failures', () => {
  it('tells the user the query failed and logs the cause', async () => {
    const failure = new Error('boom');
    service.queryWiki.mockRejectedValue(failure);
    const rendered = setup();
    await ask(rendered, 'q');
    expect(toast.error).toHaveBeenCalledExactlyOnceWith('errors.queryFailed');
    expect(consoleError).toHaveBeenCalledWith('Query failed:', failure);
    expect(rendered.result.current.isQuerying).toBe(false);
    expect(rendered.result.current.answer).toBe('');
    expect(metrics.submitted).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('adds no failure toast of its own when a risk rule held the question', async () => {
    service.queryWiki.mockRejectedValue(Object.assign(new Error('held'), { data: { code: 'risk_held' } }));
    const rendered = setup();
    await ask(rendered, 'q');
    expect(toast.error).not.toHaveBeenCalled();
    expect(rendered.result.current.isQuerying).toBe(false);
    expect(rendered.result.current.query).toBe('q');
  });
});
