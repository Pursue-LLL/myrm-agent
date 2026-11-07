/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { click, resetKit } from './wikiSectionTestKit';
import { stubProps } from './wikiSectionStubs';
import { snippetOf } from './wikiSectionFixtures';
import { WikiQueryCard } from '../WikiQueryCard';
import type { WikiQueryController } from '../useWikiQuery';

interface DrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  section?: string;
  snippet: string;
  level?: string;
  snapshotStatus?: string;
  claimStatus?: string;
  claimConfidence?: number;
  claimText?: string;
  resourceUri?: string;
  supersededFromUri?: string;
  thumbnailUrl?: string | null;
  surface: string;
  contextKey: string;
}

function renderCard(over: Partial<WikiQueryController> = {}, scope: string | null = null) {
  const wikiQuery: WikiQueryController = {
    query: '',
    setQuery: vi.fn(),
    queryMode: 'auto',
    setQueryMode: vi.fn(),
    answer: '',
    relatedArticles: [],
    sourceSnippets: [],
    queryConfidence: null,
    queryRefused: false,
    retrievalTrace: null,
    snippetDrawerState: { open: false, title: '', snippet: '' },
    setSnippetDrawerState: vi.fn(),
    isQuerying: false,
    handleQuery: vi.fn(),
    ...over,
  };
  render(<WikiQueryCard wikiQuery={wikiQuery} agentScopeId={scope} evidenceContextKey="ctx-1" />);
  return wikiQuery;
}

const input = () => screen.getByPlaceholderText<HTMLInputElement>('query.placeholder');
const submit = () => screen.getByRole<HTMLButtonElement>('button', { name: /^(actions\.query|querying)$/ });
const drawer = () => stubProps<DrawerProps & Record<string, unknown>>('SourceChunkDrawer');
const shownMode = () => document.querySelector('[data-slot="select-value"]')?.textContent;

beforeEach(resetKit);
afterEach(cleanup);

describe('WikiQueryCard: retrieval mode', () => {
  it('names the card and labels the mode picker', () => {
    renderCard();
    expect(screen.getByText('query.title')).toBeTruthy();
    expect(screen.getByText('query.description')).toBeTruthy();
    expect(screen.getByText('query.modeLabel').getAttribute('for')).toBe('wiki-query-mode');
  });

  it.each([
    ['auto', 'query.modeAuto', 'query.modeAutoHint'],
    ['raw_claim', 'query.modeRawClaim', 'query.modeRawClaimHint'],
  ] as const)('in %s mode the picker shows %s and the hint says %s', (mode, label, hint) => {
    renderCard({ queryMode: mode });
    expect(document.querySelector('[data-slot="select"]')?.getAttribute('data-value')).toBe(mode);
    expect(shownMode()).toBe(label);
    expect(screen.getAllByText(/^query\.mode\w*Hint$/).map((node) => node.textContent)).toEqual([hint]);
  });

  it('switches between automatic and raw-claim retrieval', async () => {
    const wikiQuery = renderCard();
    await click(screen.getByRole('option', { name: 'query.modeRawClaim' }));
    expect(wikiQuery.setQueryMode).toHaveBeenLastCalledWith('raw_claim');
    await click(screen.getByRole('option', { name: 'query.modeAuto' }));
    expect(wikiQuery.setQueryMode).toHaveBeenLastCalledWith('auto');
    expect(wikiQuery.setQueryMode).toHaveBeenCalledTimes(2);
  });
});

describe('WikiQueryCard: asking', () => {
  it('shows the question and reports every edit', () => {
    const wikiQuery = renderCard({ query: 'what is x' });
    expect(input().value).toBe('what is x');
    fireEvent.change(input(), { target: { value: 'what is y' } });
    expect(wikiQuery.setQuery).toHaveBeenCalledExactlyOnceWith('what is y');
  });

  it('submits on Enter and ignores other keys', () => {
    const wikiQuery = renderCard({ query: 'what is x' });
    fireEvent.keyDown(input(), { key: 'a' });
    fireEvent.keyDown(input(), { key: 'Tab' });
    expect(wikiQuery.handleQuery).not.toHaveBeenCalled();
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(wikiQuery.handleQuery).toHaveBeenCalledOnce();
  });

  it('submits from the button', async () => {
    const wikiQuery = renderCard({ query: 'what is x' });
    expect(submit().textContent).toBe('actions.query');
    expect(submit().disabled).toBe(false);
    await click(submit());
    expect(wikiQuery.handleQuery).toHaveBeenCalledOnce();
  });

  it.each([
    ['empty', ''],
    ['only blanks', '   '],
  ])('does not let a %s question be submitted from the button', (_label, query) => {
    renderCard({ query });
    expect(submit().disabled).toBe(true);
  });

  it('locks the button and says so while a question is being answered', () => {
    renderCard({ query: 'what is x', isQuerying: true });
    expect(submit().textContent).toBe('querying');
    expect(submit().disabled).toBe(true);
  });

  it('shows the answer area once there is an answer', () => {
    renderCard({ answer: 'x is a letter' });
    expect(screen.getByText('x is a letter')).toBeTruthy();
    expect(screen.getByText('query.answer')).toBeTruthy();
  });

  it('shows no answer area before the first answer', () => {
    renderCard();
    expect(screen.queryByText('query.answer')).toBeNull();
  });

  it('serves the evidence thumbnails of the scope the question was asked in', () => {
    renderCard(
      { answer: 'x is a letter', sourceSnippets: [snippetOf({ hit_kind: 'asset', asset_filename: 'chart.png' })] },
      'a1',
    );
    expect(document.querySelector('img')?.getAttribute('src')).toBe(
      'http://api.test/wiki/assets/chart.png?agent_id=a1',
    );
  });
});

describe('WikiQueryCard: evidence drawer', () => {
  it('shows the state of the drawer for the settings surface in this evidence context', () => {
    renderCard({
      snippetDrawerState: {
        open: true,
        title: 'Concept A',
        section: 'summary',
        snippet: 'the snippet',
        level: 'L1',
        snapshotStatus: 'verified',
        claimStatus: 'supported',
        claimConfidence: 0.9,
        claimText: 'the claim',
        resourceUri: 'wiki://a',
        supersededFromUri: 'wiki://old-a',
        thumbnailUrl: 'http://api.test/thumb.png',
      },
    });
    expect(drawer()).toMatchObject({
      open: true,
      title: 'Concept A',
      section: 'summary',
      snippet: 'the snippet',
      level: 'L1',
      snapshotStatus: 'verified',
      claimStatus: 'supported',
      claimConfidence: 0.9,
      claimText: 'the claim',
      resourceUri: 'wiki://a',
      supersededFromUri: 'wiki://old-a',
      thumbnailUrl: 'http://api.test/thumb.png',
      surface: 'settings',
      contextKey: 'ctx-1',
    });
  });

  it('keeps the rest of the shown snippet when the drawer opens or closes', () => {
    const wikiQuery = renderCard();
    drawer().onOpenChange(true);
    const update = vi.mocked(wikiQuery.setSnippetDrawerState).mock.calls[0][0] as (
      previous: WikiQueryController['snippetDrawerState'],
    ) => WikiQueryController['snippetDrawerState'];
    const shown = { open: true, title: 'Concept A', snippet: 'the snippet' };
    expect(update(shown)).toEqual({ ...shown, open: true });
    drawer().onOpenChange(false);
    const close = vi.mocked(wikiQuery.setSnippetDrawerState).mock.calls[1][0] as typeof update;
    expect(close(shown)).toEqual({ ...shown, open: false });
  });
});
