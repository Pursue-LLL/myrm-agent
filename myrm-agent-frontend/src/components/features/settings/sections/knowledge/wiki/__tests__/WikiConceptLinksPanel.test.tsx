/** @vitest-environment jsdom */
import type { ComponentProps } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NextIntlClientProvider } from 'next-intl';
import { WikiConceptLinksPanel } from '../WikiConceptLinksPanel';
import { wikiService } from '@/services/wikiService';
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

const renderPanel = (
  props: ComponentProps<typeof WikiConceptLinksPanel>,
  locale: keyof typeof LOCALE_MESSAGES = 'en',
) =>
  render(
    <NextIntlClientProvider
      locale={locale}
      messages={{ settings: { wiki: { concepts: { links: LOCALE_MESSAGES[locale].settings.wiki.concepts.links } } } }}
    >
      <WikiConceptLinksPanel {...props} />
    </NextIntlClientProvider>,
  );

const mockLinks = (response: Awaited<ReturnType<typeof wikiService.getConceptLinks>>) =>
  (wikiService.getConceptLinks as ReturnType<typeof vi.fn>).mockResolvedValueOnce(response);

describe('WikiConceptLinksPanel', () => {
  beforeEach(() => {
    // reset 而不是 clear：未消费的 mockResolvedValueOnce 不能泄漏到下一个用例
    vi.resetAllMocks();
  });

  it('renders backlinks with context snippet and handles tab switching', async () => {
    mockLinks({
      concept_name: 'test-concept',
      outlinks: [
        {
          name: 'outgoing-target',
          weight: 3.0,
          exists: true,
          context_snippet: null,
        },
      ],
      backlinks: [
        {
          name: 'referencing-source',
          weight: 4.5,
          exists: true,
          context_snippet: 'This document references [[test-concept]] directly.',
          heading: '采购审核机制',
          line_number: 7,
        },
      ],
      ego_graph: {
        nodes: [
          { id: 'test-concept', name: 'test concept', group: 1 },
          { id: 'referencing-source', name: 'referencing source', group: 1 },
        ],
        edges: [{ source: 'referencing-source', target: 'test-concept', weight: 4.5 }],
      },
    });

    const handleSelect = vi.fn();
    renderPanel({ conceptName: 'test-concept', agentId: 'agent-1', onSelectConcept: handleSelect });

    expect(await screen.findByText('Links and context')).toBeInTheDocument();
    expect(screen.getByText('Cited by 1 · Links to 1')).toBeInTheDocument();
    expect(screen.getByText('Cited by (1)')).toBeInTheDocument();
    // 边权重是内部指标：列表已按强度排序，不向用户展示数值
    expect(screen.queryByText(/4\.5/)).not.toBeInTheDocument();

    expect(screen.getByText('§ 采购审核机制')).toBeInTheDocument();
    expect(screen.getByText('L7')).toBeInTheDocument();
    expect(screen.getByTitle('Click the card to jump to the section: 采购审核机制')).toBeInTheDocument();

    expect(screen.getByText('referencing-source')).toBeInTheDocument();
    expect(screen.getByText(/“This document references \[\[test-concept\]\] directly\.”/)).toBeInTheDocument();

    // 点击反链项触发跳转（携带小节标题锚点）
    await userEvent.click(screen.getByText('referencing-source'));
    expect(handleSelect).toHaveBeenCalledWith('referencing-source', '采购审核机制');

    await userEvent.click(screen.getByText('Links to (1)'));
    expect(await screen.findByText('outgoing-target')).toBeInTheDocument();
    expect(screen.queryByText(/3\.0/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByText('Related (2)'));
    expect(await screen.findByText('2 concepts · 1 connection')).toBeInTheDocument();
    expect(screen.getByText('Click a concept to open it')).toBeInTheDocument();
  });

  it('renders correct empty states across all tabs', async () => {
    mockLinks({
      concept_name: 'empty-concept',
      outlinks: [],
      backlinks: [],
      ego_graph: { nodes: [], edges: [] },
    });

    renderPanel({ conceptName: 'empty-concept' });

    expect(await screen.findByText('Nothing links to this concept yet')).toBeInTheDocument();

    await userEvent.click(screen.getByText('Links to (0)'));
    expect(await screen.findByText('This concept has no links yet')).toBeInTheDocument();

    await userEvent.click(screen.getByText('Related (0)'));
    expect(await screen.findByText('No related concepts to show yet')).toBeInTheDocument();
  });

  it('disables interaction for references whose page is missing', async () => {
    mockLinks({
      concept_name: 'ghost-test',
      outlinks: [
        {
          name: 'unresolved-outlink',
          weight: 1.0,
          exists: false,
          context_snippet: null,
        },
      ],
      backlinks: [
        {
          name: 'unresolved-backlink',
          weight: 2.0,
          exists: false,
          context_snippet: 'Pending creation [[ghost-test]]',
          heading: null,
          line_number: null,
        },
      ],
      ego_graph: { nodes: [], edges: [] },
    });

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

  it('handles ego graph center node vs neighbor node click interactions', async () => {
    mockLinks({
      concept_name: 'center-node',
      outlinks: [],
      backlinks: [],
      ego_graph: {
        nodes: [
          { id: 'center-node', name: 'Center Concept', group: 1 },
          { id: 'neighbor-node', name: 'Neighbor Concept', group: 1 },
        ],
        edges: [{ source: 'center-node', target: 'neighbor-node', weight: 1.0 }],
      },
    });

    const handleSelect = vi.fn();
    renderPanel({ conceptName: 'center-node', onSelectConcept: handleSelect });

    await userEvent.click(await screen.findByText('Related (2)'));

    // 点击中心节点：不应触发 onSelectConcept
    await userEvent.click(screen.getByText('Center Concept'));
    expect(handleSelect).not.toHaveBeenCalled();

    // 点击邻居节点：应当触发 onSelectConcept('neighbor-node')
    await userEvent.click(screen.getByText('Neighbor Concept'));
    expect(handleSelect).toHaveBeenCalledWith('neighbor-node');
  });

  it('displays error banner and supports retry on fetch failure', async () => {
    (wikiService.getConceptLinks as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error('Network connection timeout'))
      .mockResolvedValueOnce({
        concept_name: 'retry-test',
        outlinks: [],
        backlinks: [],
        ego_graph: { nodes: [], edges: [] },
      });

    renderPanel({ conceptName: 'retry-test' });

    expect(await screen.findByText('Network connection timeout')).toBeInTheDocument();
    // 没有拿到数据时，不能把「0 条」与「没有链接」的空态当事实展示
    expect(screen.queryByText(/^Cited by/)).not.toBeInTheDocument();
    expect(screen.queryByText('Nothing links to this concept yet')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Refresh links' }));

    await waitFor(() => {
      expect(screen.queryByText('Network connection timeout')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Nothing links to this concept yet')).toBeInTheDocument();
  });

  it('falls back to localized copy when the failure carries no message', async () => {
    (wikiService.getConceptLinks as ReturnType<typeof vi.fn>).mockRejectedValueOnce('boom');

    renderPanel({ conceptName: 'opaque-failure' });

    expect(await screen.findByText('Failed to load links')).toBeInTheDocument();
  });

  it('renders the same panel in Chinese from the zh locale', async () => {
    mockLinks({
      concept_name: 'zh-concept',
      outlinks: [{ name: 'out', weight: 3.0, exists: true, context_snippet: null }],
      backlinks: [
        {
          name: 'src',
          weight: 4.5,
          exists: true,
          context_snippet: '见 [[zh-concept]]',
          heading: null,
          line_number: null,
        },
      ],
      ego_graph: {
        nodes: [
          { id: 'zh-concept', name: 'zh', group: 1 },
          { id: 'src', name: 'src', group: 1 },
        ],
        edges: [{ source: 'src', target: 'zh-concept', weight: 4.5 }],
      },
    });

    renderPanel({ conceptName: 'zh-concept' }, 'zh');

    expect(await screen.findByText('链接与上下文')).toBeInTheDocument();
    expect(screen.getByText('被 1 处引用 · 引用 1 处')).toBeInTheDocument();

    await userEvent.click(screen.getByText('关联概念 (2)'));
    expect(await screen.findByText('2 个概念 · 1 条关联')).toBeInTheDocument();
  });
});
