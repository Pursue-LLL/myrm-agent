import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { WikiReviewSlipModal } from '../WikiReviewSlipModal';
import { writebackService, type ReviewSlipTask } from '@/services/wikiService';

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

const TASK: ReviewSlipTask = {
  taskId: 'task-real-7',
  taskTitle: 'Billing export rework',
  candidateInsights: [
    {
      topic: 'Chunked CSV export',
      content: 'Stream rows in 5k chunks to keep memory flat.',
      rationale: 'Held at 2M rows.',
    },
    { topic: 'Timezone cutoff', content: 'Cut daily totals at the tenant timezone.', recommended_layer: 'claims' },
  ],
};

const SLIP_BATCH = {
  task_id: 'task-real-7',
  title: 'Billing export rework',
  generated_at: '2026-11-03T08:00:00Z',
  excluded_matches_count: 0,
  questions: [
    {
      question_id: 'q1',
      topic: 'Chunked CSV export',
      candidate_content: 'Stream rows in 5k chunks to keep memory flat.',
      rationale: 'Held at 2M rows.',
      selected_option_id: 'o1',
      options: [
        { id: 'o1', label: 'Methods', recommended: true, target_layer: 'methods' as const },
        { id: 'o2', label: 'Discard', recommended: false, target_layer: 'discard' as const },
      ],
    },
  ],
};

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

    render(<WikiReviewSlipModal open onOpenChange={vi.fn()} task={TASK} />);

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

    render(<WikiReviewSlipModal open onOpenChange={vi.fn()} task={TASK} />);

    expect(screen.getByText('extracting')).toBeInTheDocument();
  });

  it('asks for a slip built from exactly the task and lessons the caller gave', async () => {
    vi.mocked(writebackService.generateReviewSlips).mockResolvedValueOnce(SLIP_BATCH);

    render(<WikiReviewSlipModal open onOpenChange={vi.fn()} task={TASK} />);

    await waitFor(() => {
      expect(writebackService.generateReviewSlips).toHaveBeenCalledTimes(1);
    });
    expect(writebackService.generateReviewSlips).toHaveBeenCalledWith(
      {
        task_id: 'task-real-7',
        task_title: 'Billing export rework',
        candidate_insights: TASK.candidateInsights,
      },
      'test_scope_agent',
    );
  });

  it('commits the recommended choice for the task it was asked about', async () => {
    vi.mocked(writebackService.generateReviewSlips).mockResolvedValueOnce(SLIP_BATCH);
    vi.mocked(writebackService.applyWritebackDecisions).mockResolvedValueOnce({
      task_id: 'task-real-7',
      committed_count: 1,
      discarded_count: 0,
      created_paths: ['methods/chunked-csv-export.md'],
      message: 'ok',
    });
    const onApplied = vi.fn();

    render(<WikiReviewSlipModal open onOpenChange={vi.fn()} task={TASK} onApplied={onApplied} />);
    await waitFor(() => {
      expect(screen.getByText('Chunked CSV export')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'confirm' }));

    await waitFor(() => {
      expect(onApplied).toHaveBeenCalledTimes(1);
    });
    expect(writebackService.applyWritebackDecisions).toHaveBeenCalledWith(
      {
        task_id: 'task-real-7',
        decisions: [
          {
            question_id: 'q1',
            selected_option_id: 'o1',
            target_layer: 'methods',
            candidate_title: 'Chunked CSV export',
            candidate_content: 'Stream rows in 5k chunks to keep memory flat.',
          },
        ],
      },
      'test_scope_agent',
    );
  });

  it('does not ask for a slip while it is closed', () => {
    render(<WikiReviewSlipModal open={false} onOpenChange={vi.fn()} task={TASK} />);

    expect(writebackService.generateReviewSlips).not.toHaveBeenCalled();
  });
});
