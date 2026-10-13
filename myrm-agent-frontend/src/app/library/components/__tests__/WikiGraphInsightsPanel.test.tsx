/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import WikiGraphInsightsPanel from '../WikiGraphInsightsPanel';
import { wikiService, type WikiGraphInsights } from '@/services/wikiService';
import en from '../../../../../locales/en.json';
import zh from '../../../../../locales/zh.json';

// The global setup stubs next-intl with an identity translator; this suite asserts the real locale copy.
vi.mock('next-intl', async (importOriginal) => importOriginal<typeof import('next-intl')>());

vi.mock('@/services/wikiService', () => ({
  wikiService: { getGraphInsights: vi.fn() },
}));

const LOCALE_MESSAGES = { en, zh } as const;

const INSIGHTS: WikiGraphInsights = {
  unexpected_connections: [{ source: 'rust/ownership', target: 'cooking/pasta', weight: 7.5 }],
  knowledge_gaps: [{ node: 'notes/lone-page', type: 'isolated', degree: 0 }],
  communities: [
    {
      id: 4,
      size: 12,
      cohesion: 0.4,
      members: [
        'rust/ownership',
        'rust/borrowing',
        'rust/lifetimes',
        'rust/traits',
        'rust/generics',
        'rust/macros',
        'rust/async',
        'rust/unsafe',
        'rust/modules',
        'rust/testing',
      ],
    },
  ],
};

const renderPanel = (locale: keyof typeof LOCALE_MESSAGES, onSelectNode?: (nodeId: string) => void) =>
  render(
    <NextIntlClientProvider locale={locale} messages={{ library: { graph: LOCALE_MESSAGES[locale].library.graph } }}>
      <WikiGraphInsightsPanel agentId="agent-1" onSelectNode={onSelectNode} />
    </NextIntlClientProvider>,
  );

describe('WikiGraphInsightsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(wikiService.getGraphInsights).mockResolvedValue(INSIGHTS);
  });

  it('names a cluster after its hub page and reports size, cohesion and hidden members', async () => {
    renderPanel('en');

    expect(await screen.findByText('12 concepts · Cohesion 40%')).toBeInTheDocument();
    expect(screen.getAllByText('rust/ownership').length).toBeGreaterThan(0);
    expect(screen.getByText('rust/borrowing')).toBeInTheDocument();
    expect(screen.getByText('rust/generics')).toBeInTheDocument();
    expect(screen.queryByText('rust/macros')).not.toBeInTheDocument();
    expect(screen.getByText('+7')).toBeInTheDocument();
  });

  it('shows no internal identifiers or raw metrics', async () => {
    renderPanel('en');
    await screen.findByText('12 concepts · Cohesion 40%');

    expect(screen.queryByText(/Cluster #/)).not.toBeInTheDocument();
    expect(screen.queryByText(/w=/)).not.toBeInTheDocument();
    expect(screen.queryByText(/7\.5/)).not.toBeInTheDocument();
  });

  it('renders the cluster summary in Chinese', async () => {
    renderPanel('zh');

    expect(await screen.findByText('12 个概念 · 内聚度 40%')).toBeInTheDocument();
  });

  it('locates a page when its name is clicked', async () => {
    const onSelectNode = vi.fn();
    renderPanel('en', onSelectNode);
    await screen.findByText('12 concepts · Cohesion 40%');

    fireEvent.click(screen.getByText('rust/lifetimes'));

    expect(onSelectNode).toHaveBeenCalledWith('rust/lifetimes');
  });
});
