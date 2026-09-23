import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WikiLayersLedgerPanel } from '../WikiLayersLedgerPanel';
import { writebackService } from '@/services/wikiService';

vi.mock('@/services/wikiService', () => ({
  writebackService: {
    getLayersStats: vi.fn(),
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

    // 验证标题与 WorkBuddy 架构徽章
    expect(screen.getByText('五层知识资产全局态势')).toBeInTheDocument();
    expect(screen.getByText('WorkBuddy 架构')).toBeInTheDocument();

    // 验证五大物理分层
    expect(screen.getByText('原始输入与候选池')).toBeInTheDocument();
    expect(screen.getByText('来源凭证卡')).toBeInTheDocument();
    expect(screen.getByText('核心知识体系')).toBeInTheDocument();
    expect(screen.getByText('观点与主张')).toBeInTheDocument();
    expect(screen.getByText('交付物与使用台账')).toBeInTheDocument();

    // 验证负向硬拦截提示
    expect(screen.getByText(/负向不回写硬拦截/)).toBeInTheDocument();

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

    render(<WikiLayersLedgerPanel />);
    const user = userEvent.setup();

    const openBtn = screen.getByRole('button', { name: /打开作者审阅单/ });
    await user.click(openBtn);

    // 验证审阅单浮窗标题弹出
    await waitFor(() => {
      expect(screen.getByText('作者审阅单 (Review Slip)')).toBeInTheDocument();
    });
  });
});
