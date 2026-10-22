/** @vitest-environment jsdom */
import type { ComponentProps } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NextIntlClientProvider } from 'next-intl';
import { WikiConceptLinksPanel } from '../WikiConceptLinksPanel';
import {
  wikiService,
  type ConceptBacklinkItem,
  type ConceptLinksResponse,
  type ConceptLinkItem,
} from '@/services/wikiService';
import en from '../../../../../../../../locales/en.json';
import zh from '../../../../../../../../locales/zh.json';

// The global setup stubs next-intl with an identity translator; this suite asserts the real locale copy.
vi.mock('next-intl', async (importOriginal) => importOriginal<typeof import('next-intl')>());

vi.mock('@/services/wikiService', () => ({
  wikiService: {
    getConceptLinks: vi.fn(),
  },
}));

const LOCALE_MESSAGES = { en, zh } as const;

const panelTree = (
  props: ComponentProps<typeof WikiConceptLinksPanel>,
  locale: keyof typeof LOCALE_MESSAGES = 'en',
) => (
  <NextIntlClientProvider
    locale={locale}
    messages={{ settings: { wiki: { concepts: { links: LOCALE_MESSAGES[locale].settings.wiki.concepts.links } } } }}
  >
    <WikiConceptLinksPanel {...props} />
  </NextIntlClientProvider>
);

const renderPanel = (
  props: ComponentProps<typeof WikiConceptLinksPanel>,
  locale: keyof typeof LOCALE_MESSAGES = 'en',
) => render(panelTree(props, locale));

const getConceptLinksMock = () => wikiService.getConceptLinks as ReturnType<typeof vi.fn>;

const mockLinks = (response: ConceptLinksResponse) => getConceptLinksMock().mockResolvedValueOnce(response);

const outlink = (name: string, overrides: Partial<ConceptLinkItem> = {}): ConceptLinkItem => ({
  name,
  exists: true,
  ...overrides,
});

const backlink = (name: string, overrides: Partial<ConceptBacklinkItem> = {}): ConceptBacklinkItem => ({
  name,
  exists: true,
  context_snippet: null,
  heading: null,
  ...overrides,
});

const linksOf = (
  concept_name: string,
  {
    outlinks = [],
    backlinks = [],
    outlinksHasMore = false,
    backlinksHasMore = false,
  }: {
    outlinks?: ConceptLinkItem[];
    backlinks?: ConceptBacklinkItem[];
    outlinksHasMore?: boolean;
    backlinksHasMore?: boolean;
  } = {},
): ConceptLinksResponse => ({
  concept_name,
  outlinks,
  backlinks,
  outlinks_has_more: outlinksHasMore,
  backlinks_has_more: backlinksHasMore,
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

describe('WikiConceptLinksPanel', () => {
  beforeEach(() => {
    // reset 而不是 clear：未消费的 mockResolvedValueOnce 不能泄漏到下一个用例
    vi.resetAllMocks();
  });

  it('renders backlinks with context snippet and handles tab switching', async () => {
    mockLinks(
      linksOf('test-concept', {
        outlinks: [outlink('outgoing-target')],
        backlinks: [
          backlink('referencing-source', {
            context_snippet: 'This document references [[test-concept]] directly.',
            heading: '采购审核机制',
          }),
        ],
      }),
    );

    const handleSelect = vi.fn();
    renderPanel({ conceptName: 'test-concept', agentId: 'agent-1', onSelectConcept: handleSelect });

    expect(await screen.findByText('Links and context')).toBeInTheDocument();
    expect(screen.getByText('Cited by 1 · Links to 1')).toBeInTheDocument();
    expect(screen.getByText('Cited by (1)')).toBeInTheDocument();

    expect(screen.getByText('§ 采购审核机制')).toBeInTheDocument();
    expect(screen.getByTitle('Click the card to jump to the section: 采购审核机制')).toBeInTheDocument();

    expect(screen.getByText('referencing-source')).toBeInTheDocument();
    expect(screen.getByText(/“This document references \[\[test-concept\]\] directly\.”/)).toBeInTheDocument();

    // 点击反链项触发跳转（携带小节标题锚点）
    await userEvent.click(screen.getByText('referencing-source'));
    expect(handleSelect).toHaveBeenCalledWith('referencing-source', '采购审核机制');

    await userEvent.click(screen.getByText('Links to (1)'));
    expect(await screen.findByText('outgoing-target')).toBeInTheDocument();
    expect(screen.queryByText('Related (0)')).not.toBeInTheDocument();
  });

  it('exposes the two directions as an accessible tab set that arrow keys move through', async () => {
    mockLinks(
      linksOf('keyboard-concept', {
        outlinks: [outlink('outgoing-target')],
        backlinks: [backlink('referencing-source')],
      }),
    );
    renderPanel({ conceptName: 'keyboard-concept' });

    const tablist = await screen.findByRole('tablist', { name: 'Links and context' });
    const [citedBy, linksTo] = within(tablist).getAllByRole('tab');
    expect(citedBy).toHaveAccessibleName('Cited by (1)');
    expect(citedBy).toHaveAttribute('aria-selected', 'true');
    expect(linksTo).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('tabpanel', { name: 'Cited by (1)' })).toHaveTextContent('referencing-source');

    await userEvent.click(citedBy);
    await userEvent.keyboard('{ArrowRight}');

    expect(linksTo).toHaveAttribute('aria-selected', 'true');
    expect(linksTo).toHaveFocus();
    expect(screen.getByRole('tabpanel', { name: 'Links to (1)' })).toHaveTextContent('outgoing-target');

    await userEvent.keyboard('{ArrowLeft}');

    expect(citedBy).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveTextContent('referencing-source');
  });

  it('shows no tabs and no counts when the first load fails', async () => {
    getConceptLinksMock().mockRejectedValueOnce(new Error('boom'));

    renderPanel({ conceptName: 'broken' });

    expect(await screen.findByText('Failed to load links')).toBeInTheDocument();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
    expect(screen.queryByRole('tabpanel')).not.toBeInTheDocument();
  });

  it('renders correct empty states across all tabs', async () => {
    mockLinks(linksOf('empty-concept'));

    renderPanel({ conceptName: 'empty-concept' });

    expect(await screen.findByText('Nothing links to this concept yet')).toBeInTheDocument();

    await userEvent.click(screen.getByText('Links to (0)'));
    expect(await screen.findByText('This concept has no links yet')).toBeInTheDocument();
  });

  it('adds a trailing plus only to the direction the server cut at its cap', async () => {
    const backlinks = Array.from({ length: 100 }, (_, index) => backlink(`source-${index}`));
    mockLinks(linksOf('hub', { backlinks, outlinks: [outlink('leaf')], backlinksHasMore: true }));

    renderPanel({ conceptName: 'hub' });

    expect(await screen.findByText('Cited by 100+ · Links to 1')).toBeInTheDocument();
    expect(screen.getByText('Cited by (100+)')).toBeInTheDocument();
    expect(screen.getByText('Links to (1)')).toBeInTheDocument();
  });

  it('disables interaction for references whose page is missing', async () => {
    mockLinks(
      linksOf('ghost-test', {
        outlinks: [outlink('unresolved-outlink', { exists: false })],
        backlinks: [
          backlink('unresolved-backlink', {
            exists: false,
            context_snippet: 'Pending creation [[ghost-test]]',
            heading: null,
          }),
        ],
      }),
    );

    const handleSelect = vi.fn();
    renderPanel({ conceptName: 'ghost-test', onSelectConcept: handleSelect });

    expect(await screen.findByText('Missing')).toBeInTheDocument();
    const backlinkBtn = screen.getByText('unresolved-backlink').closest('button');
    expect(backlinkBtn).toBeDisabled();
    await userEvent.click(backlinkBtn as HTMLButtonElement);
    expect(handleSelect).not.toHaveBeenCalled();

    await userEvent.click(screen.getByText('Links to (1)'));
    expect(await screen.findByText('Missing')).toBeInTheDocument();
    const outlinkBtn = screen.getByText('unresolved-outlink').closest('button');
    expect(outlinkBtn).toBeDisabled();
    await userEvent.click(outlinkBtn as HTMLButtonElement);
    expect(handleSelect).not.toHaveBeenCalled();
  });

  it('shows localized copy instead of the server message when loading fails, and supports retry', async () => {
    getConceptLinksMock()
      .mockRejectedValueOnce(new Error('Failed to fetch concept links'))
      .mockResolvedValueOnce(linksOf('retry-test'));

    renderPanel({ conceptName: 'retry-test' });

    expect(await screen.findByText('Failed to load links')).toBeInTheDocument();
    expect(screen.queryByText('Failed to fetch concept links')).not.toBeInTheDocument();
    // 没有拿到数据时，不能把「0 条」与「没有链接」的空态当事实展示
    expect(screen.queryByText(/^Cited by/)).not.toBeInTheDocument();
    expect(screen.queryByText('Nothing links to this concept yet')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Refresh links' }));

    await waitFor(() => {
      expect(screen.queryByText('Failed to load links')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Nothing links to this concept yet')).toBeInTheDocument();
  });

  it('hides the previous concept while the next one loads and keeps the chosen tab', async () => {
    mockLinks(linksOf('first', { outlinks: [outlink('first-out')], backlinks: [backlink('first-back')] }));
    const view = renderPanel({ conceptName: 'first' });
    await userEvent.click(await screen.findByText('Links to (1)'));
    expect(screen.getByText('first-out')).toBeInTheDocument();

    const next = deferred<ConceptLinksResponse>();
    getConceptLinksMock().mockReturnValueOnce(next.promise);
    view.rerender(panelTree({ conceptName: 'second' }));

    expect(screen.queryByText('first-out')).not.toBeInTheDocument();
    expect(screen.queryByText('Links to (1)')).not.toBeInTheDocument();

    await act(async () => {
      next.resolve(linksOf('second', { outlinks: [outlink('second-out')], backlinks: [backlink('second-back')] }));
    });

    expect(await screen.findByText('second-out')).toBeInTheDocument();
    expect(screen.queryByText('second-back')).not.toBeInTheDocument();
  });

  it('ignores a late response for a concept the panel has already moved away from', async () => {
    const first = deferred<ConceptLinksResponse>();
    getConceptLinksMock().mockReturnValueOnce(first.promise);
    const view = renderPanel({ conceptName: 'first' });

    mockLinks(linksOf('second', { backlinks: [backlink('second-back')] }));
    view.rerender(panelTree({ conceptName: 'second' }));
    expect(await screen.findByText('second-back')).toBeInTheDocument();

    await act(async () => {
      first.resolve(linksOf('first', { backlinks: [backlink('first-back')] }));
    });

    expect(screen.getByText('second-back')).toBeInTheDocument();
    expect(screen.queryByText('first-back')).not.toBeInTheDocument();
  });

  it('renders the same panel in Chinese from the zh locale', async () => {
    mockLinks(
      linksOf('zh-concept', {
        outlinks: [outlink('out')],
        backlinks: [backlink('src', { context_snippet: '见 [[zh-concept]]' })],
      }),
    );

    renderPanel({ conceptName: 'zh-concept' }, 'zh');

    expect(await screen.findByText('链接与上下文')).toBeInTheDocument();
    expect(screen.getByText('被 1 处引用 · 引用 1 处')).toBeInTheDocument();
    expect(screen.getByText('被引用 (1)')).toBeInTheDocument();
    expect(screen.getByText('引用了 (1)')).toBeInTheDocument();
  });
});
