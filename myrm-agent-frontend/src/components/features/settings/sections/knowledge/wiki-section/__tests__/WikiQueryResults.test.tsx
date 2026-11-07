/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { formatClaimConfidence } from '@/lib/wiki/claimStatusDisplay';
import { click, resetKit, world } from './wikiSectionTestKit';
import { snippetOf } from './wikiSectionFixtures';
import { WikiQueryResults } from '../WikiQueryResults';

type ResultsQuery = Parameters<typeof WikiQueryResults>[0]['wikiQuery'];

function renderResults(over: Partial<ResultsQuery> = {}, scope: string | null = null) {
  const wikiQuery: ResultsQuery = {
    answer: 'The answer',
    queryRefused: false,
    queryConfidence: null,
    retrievalTrace: null,
    sourceSnippets: [],
    relatedArticles: [],
    setSnippetDrawerState: vi.fn(),
    ...over,
  };
  const { container } = render(<WikiQueryResults wikiQuery={wikiQuery} agentScopeId={scope} />);
  return { wikiQuery, container };
}

const answerBox = () => screen.getByText('The answer');
const confidenceLabel = () => screen.queryByText(/^query\.confidenceScore/);

beforeEach(resetKit);
afterEach(cleanup);

describe('WikiQueryResults: the answer', () => {
  it('renders nothing while there is no answer, whatever else is known', () => {
    const { container } = renderResults({
      answer: '',
      queryConfidence: 0.9,
      queryRefused: true,
      relatedArticles: ['Alpha'],
      sourceSnippets: [snippetOf()],
    });
    expect(container.childElementCount).toBe(0);
  });

  it('shows the answer under its heading, keeping its line breaks', () => {
    renderResults({ answer: 'line one\nline two' });
    expect(screen.getByText('query.answer')).toBeTruthy();
    const box = screen.getByText(/line one/);
    expect(box.textContent).toBe('line one\nline two');
    expect(box.className).toContain('whitespace-pre-wrap');
  });

  it('shows a normal answer on the neutral background', () => {
    renderResults();
    expect(answerBox().className).toContain('bg-muted');
    expect(answerBox().className).not.toContain('destructive');
    expect(screen.queryByText('query.refusedLabel')).toBeNull();
  });

  it('marks a refused answer with the destructive text label and block', () => {
    renderResults({ queryRefused: true, queryConfidence: 0.4 });
    expect(screen.getByText('query.refusedLabel').className).toContain('text-destructive-text');
    expect(answerBox().className).toContain('border-destructive/40');
    expect(answerBox().className).toContain('bg-destructive/5');
    expect(answerBox().className).not.toContain('bg-muted');
    expect(confidenceLabel()).toBeNull();
  });
});

describe('WikiQueryResults: confidence', () => {
  it.each(['en', 'de'])('says how confident the answer is, formatted for the %s locale', (locale) => {
    world.locale = locale;
    renderResults({ queryConfidence: 0.85 });
    const value = formatClaimConfidence(0.85, locale);
    expect(confidenceLabel()?.textContent).toBe(`query.confidenceScore|${JSON.stringify({ value })}`);
  });

  it('reports zero confidence instead of hiding it', () => {
    renderResults({ queryConfidence: 0 });
    expect(confidenceLabel()?.textContent).toBe(`query.confidenceScore|${JSON.stringify({ value: '0%' })}`);
  });

  it('shows no confidence when the server gave none', () => {
    renderResults({ queryConfidence: null });
    expect(confidenceLabel()).toBeNull();
  });
});

describe('WikiQueryResults: related articles', () => {
  it('lists the related articles in order under their heading', () => {
    renderResults({ relatedArticles: ['Beta', 'Alpha', 'Beta'] });
    expect(screen.getByText('query.relatedArticles')).toBeTruthy();
    expect(screen.getAllByText(/^(Alpha|Beta)$/).map((chip) => chip.textContent)).toEqual(['Beta', 'Alpha', 'Beta']);
  });

  it('shows no heading without related articles', () => {
    renderResults();
    expect(screen.queryByText('query.relatedArticles')).toBeNull();
  });
});

describe('WikiQueryResults: evidence', () => {
  it('shows the retrieval trace and the source snippets of the answer', () => {
    renderResults({
      retrievalTrace: { index_hits: [], seeds: [], sidecar_directories: [], selected_concepts: ['Concept A'] },
      sourceSnippets: [snippetOf({ name: 'Snippet A' })],
    });
    expect(screen.getByText('query.retrievalTraceTitle')).toBeTruthy();
    expect(screen.getByText('Snippet A')).toBeTruthy();
  });

  it('shows neither without trace or snippets', () => {
    renderResults();
    expect(screen.queryByText('query.retrievalTraceTitle')).toBeNull();
    expect(screen.queryByText('sources_title')).toBeNull();
  });

  it('hands a clicked snippet to the drawer of the page', async () => {
    const { wikiQuery } = renderResults({ sourceSnippets: [snippetOf({ name: 'Snippet A' })] });
    await click(screen.getByRole('button', { name: /Snippet A/ }));
    expect(wikiQuery.setSnippetDrawerState).toHaveBeenCalledOnce();
    expect(vi.mocked(wikiQuery.setSnippetDrawerState).mock.calls[0][0]).toMatchObject({
      open: true,
      title: 'Snippet A',
    });
  });

  it('builds asset thumbnails for the scope of the page', () => {
    renderResults({ sourceSnippets: [snippetOf({ hit_kind: 'asset', asset_filename: 'chart.png' })] }, 'a1');
    expect(document.querySelector('img')?.getAttribute('src')).toBe(
      'http://api.test/wiki/assets/chart.png?agent_id=a1',
    );
  });
});
