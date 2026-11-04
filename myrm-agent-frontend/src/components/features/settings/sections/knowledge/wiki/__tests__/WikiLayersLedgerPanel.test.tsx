import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WikiLayersLedgerPanel } from '../WikiLayersLedgerPanel';
import { layersService } from '@/services/wikiService';

const stableT = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${Object.values(values).join('|')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/wikiService', () => ({
  layersService: {
    getLayersStats: vi.fn(),
    getLayerItems: vi.fn(),
  },
}));

vi.mock('../../WikiAgentScopeContext', () => ({
  useWikiAgentScope: () => ({
    agentScopeId: 'test_scope_agent',
    scopeRevision: 1,
    scopeLabel: 'Test Agent',
  }),
}));

describe('WikiLayersLedgerPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders 5-layer topology and loads stats correctly', async () => {
    vi.mocked(layersService.getLayersStats).mockResolvedValueOnce({
      agent_id: 'test_scope_agent',
      raw_files_count: 8,
      sources_count: 14,
      concepts_count: 25,
      claims_count: 6,
      methods_count: 5,
      templates_count: 3,
      deliverables_count: 12,
      inbox_count: 2,
    });

    render(<WikiLayersLedgerPanel />);

    // 标题与架构徽章走翻译
    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('architectureBadge')).toBeInTheDocument();

    // 五大物理分层的标题、副标题、徽标、说明都走翻译
    for (const layer of ['l1', 'l2', 'l3', 'l4', 'l5']) {
      for (const field of ['title', 'subtext', 'badge', 'description']) {
        expect(screen.getByText(`layers.${layer}.${field}`)).toBeInTheDocument();
      }
    }

    // 等待异步统计数据加载并校验计数
    await waitFor(() => {
      expect(layersService.getLayersStats).toHaveBeenCalledWith('test_scope_agent');
      // L1: raw (8) + inbox (2) = 10
      expect(screen.getByText('10')).toBeInTheDocument();
      // L2: sources (14)
      expect(screen.getByText('14')).toBeInTheDocument();
      // L3: concepts (25) + methods (5) = 30
      expect(screen.getByText('30')).toBeInTheDocument();
      // L4: claims (6)
      expect(screen.getByText('6')).toBeInTheDocument();
      // L5: deliverables (12)
      expect(screen.getByText('12')).toBeInTheDocument();
    });
  });

  it('drills into a layer and previews an entry with translated labels', async () => {
    vi.mocked(layersService.getLayersStats).mockResolvedValueOnce({
      agent_id: 'test_scope_agent',
      raw_files_count: 0,
      sources_count: 0,
      concepts_count: 1,
      claims_count: 0,
      methods_count: 0,
      templates_count: 0,
      deliverables_count: 0,
      inbox_count: 0,
    });
    vi.mocked(layersService.getLayerItems).mockResolvedValueOnce([
      {
        slug: 'retry-policy',
        title: 'Retry policy',
        relative_path: 'concepts/retry-policy.md',
        publish_status: 'draft',
        content_snippet: '',
        updated_at: '',
      },
    ]);

    render(<WikiLayersLedgerPanel />);
    const user = userEvent.setup();

    await user.click(screen.getAllByRole('button', { name: /^viewLayerItems:/ })[0]);

    // 列表头、数量、空摘要与时间的兜底都走翻译
    await waitFor(() => {
      expect(screen.getByText('drawerTitle:layers.l1.title')).toBeInTheDocument();
    });
    expect(screen.getByText('itemCount:1')).toBeInTheDocument();
    expect(screen.getByText('noSnippet')).toBeInTheDocument();
    expect(screen.getByText('justNow')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'previewItem:Retry policy' }));

    const preview = screen.getByRole('dialog', { name: 'ariaLabel' });
    expect(preview).toHaveTextContent('updatedAt:justNow');
    expect(preview).toHaveTextContent('storageLayer:layers.l1.title');
    expect(screen.getByRole('button', { name: 'copyPath' })).toBeInTheDocument();
  });
});
