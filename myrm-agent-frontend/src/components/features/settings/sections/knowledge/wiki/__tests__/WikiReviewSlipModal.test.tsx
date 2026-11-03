import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { WikiReviewSlipModal } from '../WikiReviewSlipModal';
import { writebackService } from '@/services/wikiService';

const stableT = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${Object.values(values).join('|')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

vi.mock('@/services/wikiService', () => ({
  writebackService: {
    generateReviewSlips: vi.fn(),
    applyWritebackDecisions: vi.fn(),
  },
}));

vi.mock('../../WikiAgentScopeContext', () => ({
  useWikiAgentScope: () => ({ agentScopeId: 'test_scope_agent', scopeRevision: 1, scopeLabel: 'Test Agent' }),
}));

describe('WikiReviewSlipModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('labels the header, each question, the recommended option and the footer through translations', async () => {
    vi.mocked(writebackService.generateReviewSlips).mockResolvedValueOnce({
      task_id: 'task-1',
      title: 'slip',
      generated_at: '2026-11-03T08:00:00Z',
      excluded_matches_count: 0,
      questions: [
        {
          question_id: 'q1',
          topic: 'Dual-write migration',
          candidate_content: 'Write to both stores, verify, switch, cut over.',
          rationale: 'Verified on a core system delivery.',
          selected_option_id: 'o1',
          options: [
            { id: 'o1', label: 'Methods', recommended: true, target_layer: 'methods' },
            { id: 'o2', label: 'Discard', recommended: false, target_layer: 'discard' },
          ],
        },
      ],
    });

    render(<WikiReviewSlipModal open onOpenChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('pendingLayer')).toBeInTheDocument();
    });
    expect(screen.getByText('engineLabel')).toBeInTheDocument();
    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('description')).toBeInTheDocument();
    expect(screen.getByText('recommended')).toBeInTheDocument();
    expect(screen.getByText('footerNote')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'later' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'confirm' })).toBeEnabled();
    expect(screen.queryByText('exclusionTitle:0')).not.toBeInTheDocument();
  });

  it('shows the loading text while the slip is being generated', () => {
    vi.mocked(writebackService.generateReviewSlips).mockReturnValueOnce(new Promise(() => undefined));

    render(<WikiReviewSlipModal open onOpenChange={vi.fn()} />);

    expect(screen.getByText('extracting')).toBeInTheDocument();
  });
});
