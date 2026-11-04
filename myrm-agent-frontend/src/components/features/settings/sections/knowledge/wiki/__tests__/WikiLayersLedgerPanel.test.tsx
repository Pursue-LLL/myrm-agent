import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WikiLayersLedgerPanel } from '../WikiLayersLedgerPanel';
import { writebackService, type ReviewSlipTask } from '@/services/wikiService';

const stableT = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${Object.values(values).join('|')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/wikiService', () => ({
  writebackService: {
    getLayersStats: vi.fn(),
    getLayerItems: vi.fn(),
    generateReviewSlips: vi.fn(),
    applyWritebackDecisions: vi.fn(),
  },
}));

vi.mock('../../WikiAgentScopeContext', () => ({
  useWikiAgentScope: () => ({
    agentScopeId: 'test_scope_agent',
    scopeRevision: 1,
    scopeLabel: 'Test Agent',
  }),
}));

const REVIEW_TASK: ReviewSlipTask = {
  taskId: 'task_modal_01',
  taskTitle: 'Billing export rework',
  candidateInsights: [{ topic: 'Chunked CSV export', content: 'Stream rows in 5k chunks.' }],
};

const EMPTY_STATS = {
  agent_id: 'test_scope_agent',
  raw_files_count: 0,
  sources_count: 0,
  concepts_count: 0,
  claims_count: 0,
  methods_count: 0,
  templates_count: 0,
  deliverables_count: 0,
  inbox_count: 0,
};

describe('WikiLayersLedgerPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders 5-layer topology and loads stats correctly', async () => {
    vi.mocked(writebackService.getLayersStats).mockResolvedValueOnce({
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

    // 负向硬拦截提示
    expect(screen.getByText('blockNoticeRule')).toBeInTheDocument();

    // 等待异步统计数据加载并校验计数
    await waitFor(() => {
      expect(writebackService.getLayersStats).toHaveBeenCalledWith('test_scope_agent');
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

  it.each([
    ['no task is given', undefined],
    ['the task has no lessons to file', { ...REVIEW_TASK, candidateInsights: [] }],
  ])('offers no review slip when %s, and never asks the backend for one', async (_label, reviewTask) => {
    vi.mocked(writebackService.getLayersStats).mockResolvedValueOnce(EMPTY_STATS);

    render(<WikiLayersLedgerPanel reviewTask={reviewTask} />);
    await waitFor(() => {
      expect(writebackService.getLayersStats).toHaveBeenCalled();
    });

    expect(screen.queryByRole('button', { name: 'openReviewSlip' })).not.toBeInTheDocument();
    expect(screen.queryByText('reviewSlipGuide')).not.toBeInTheDocument();
    expect(screen.queryByText('engineLabel')).not.toBeInTheDocument();
    expect(writebackService.generateReviewSlips).not.toHaveBeenCalled();
  });

  it('opens review slip modal on button click', async () => {
    vi.mocked(writebackService.getLayersStats).mockResolvedValueOnce({
      agent_id: 'test_scope_agent',
      raw_files_count: 0,
      sources_count: 0,
      concepts_count: 0,
      claims_count: 0,
      methods_count: 0,
      templates_count: 0,
      deliverables_count: 0,
      inbox_count: 0,
    });

    vi.mocked(writebackService.generateReviewSlips).mockResolvedValueOnce({
      task_id: 'task_modal_01',
      title: '经验萃取',
      generated_at: '2026-09-23T10:00:00Z',
      questions: [],
      excluded_matches_count: 1,
    });

    render(<WikiLayersLedgerPanel reviewTask={REVIEW_TASK} />);
    const user = userEvent.setup();

    const openBtn = screen.getByRole('button', { name: 'openReviewSlip' });
    await user.click(openBtn);

    // 审阅单浮窗弹出，且已被拦截的杂质数量带进翻译
    await waitFor(() => {
      expect(screen.getByText('engineLabel')).toBeInTheDocument();
    });
    expect(screen.getByText('exclusionTitle:1')).toBeInTheDocument();
    expect(screen.getByText('noQuestions')).toBeInTheDocument();
  });

  it('drills into a layer and previews an entry with translated labels', async () => {
    vi.mocked(writebackService.getLayersStats).mockResolvedValueOnce({
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
    vi.mocked(writebackService.getLayerItems).mockResolvedValueOnce([
      {
        slug: 'retry-policy',
        title: 'Retry policy',
        relative_path: 'concepts/retry-policy.md',
        file_type: 'markdown',
        publish_status: 'draft',
        content_snippet: '',
        updated_at: '',
        source_task_id: 'task-abcdef123456',
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
    expect(preview).toHaveTextContent('taskBadge:123456');
    expect(preview).toHaveTextContent('updatedAt:justNow');
    expect(preview).toHaveTextContent('storageLayer:layers.l1.title');
    expect(preview).toHaveTextContent('fileType:fileTypeMarkdown');
    expect(preview).toHaveTextContent('sourceTask:task-abcdef123456');
    expect(screen.getByRole('button', { name: 'copyPath' })).toBeInTheDocument();
  });
});
