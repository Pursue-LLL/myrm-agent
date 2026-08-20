/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { DailyJournalData } from '@/services/statistics';

import DailyJournal from '../DailyJournal';

const modeKeys: Record<string, string> = {
  fast: 'Fast Search',
  agent: 'AI Agent',
  deep_research: 'Deep Research',
};

vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => {
    const t = (key: string): string => {
      if (namespace === 'mode') {
        return modeKeys[key] ?? key;
      }
      if (namespace === 'growthDashboard.dailyJournal') {
        const labels: Record<string, string> = {
          today: 'Today',
          tokens: 'Tokens',
          timeline: 'Timeline',
          empty: 'No activity on this day',
          typeLabels: '',
          'typeLabels.session': 'Session',
          'typeLabels.approval': 'Approval',
          'typeLabels.cron': 'Cron',
          'typeLabels.kanban': 'Kanban',
        };
        return labels[key] ?? key;
      }
      return key;
    };
    t.has = (key: string): boolean => (namespace === 'mode' ? key in modeKeys : true);
    return t;
  },
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/services/statistics', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/statistics')>();
  return {
    ...actual,
    getDailyJournal: vi.fn(),
  };
});

vi.mock('../DailyWrapCard', () => ({
  default: () => <div data-testid="daily-wrap" />,
}));

import { getDailyJournal } from '@/services/statistics';

const getDailyJournalMock = vi.mocked(getDailyJournal);

const BASE_JOURNAL: DailyJournalData = {
  date: '2026-08-16',
  overview: {
    total_sessions: 2,
    total_tokens: 1500,
    total_cost_usd: 0.012,
    total_tool_calls: 5,
    total_approvals: 1,
    total_cron_runs: 1,
    total_kanban_events: 1,
    sessions_by_source: { web: 2 },
  },
  sessions: [],
  approvals: [],
  cron_runs: [],
  kanban_events: [],
  timeline: [],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('DailyJournal', () => {
  it('localizes known action mode and timeline type labels', async () => {
    getDailyJournalMock.mockResolvedValue({
      ...BASE_JOURNAL,
      timeline: [
        {
          time: '2026-08-16T10:00:00',
          type: 'session',
          title: 'Morning research',
          detail: { tokens: 1200, action_mode: 'deep_research' },
        },
      ],
    });

    render(<DailyJournal />);

    await waitFor(() => {
      expect(screen.getByText('Morning research')).toBeInTheDocument();
    });

    expect(screen.getByText(/Deep Research/)).toBeInTheDocument();
    expect(screen.getByText(/1,200/)).toBeInTheDocument();
    expect(screen.getByText(/1,200.*Tokens/)).toBeInTheDocument();
    expect(screen.getByText('Session')).toBeInTheDocument();
  });

  it('falls back to raw action mode for unknown enums', async () => {
    getDailyJournalMock.mockResolvedValue({
      ...BASE_JOURNAL,
      timeline: [
        {
          time: '2026-08-16T09:00:00',
          type: 'session',
          title: 'Custom flow',
          detail: { tokens: 300, action_mode: 'future_custom_mode' },
        },
      ],
    });

    render(<DailyJournal />);

    await waitFor(() => {
      expect(screen.getByText('Custom flow')).toBeInTheDocument();
    });

    expect(screen.getByText(/future_custom_mode/)).toBeInTheDocument();
  });

  it('renders timeline type labels for non-session rows', async () => {
    getDailyJournalMock.mockResolvedValue({
      ...BASE_JOURNAL,
      timeline: [
        {
          time: '2026-08-16T08:00:00',
          type: 'approval',
          title: 'File write approved',
          detail: { id: 'a1', severity: 'medium', reason: 'ok', status: 'approved' },
        },
        {
          time: '2026-08-16T07:00:00',
          type: 'cron_run',
          title: 'Scheduled check',
          detail: { id: 'c1', duration_ms: 500, status: 'completed', tokens: 0, job_id: 'j1', trigger_source: null },
        },
        {
          time: '2026-08-16T06:00:00',
          type: 'kanban',
          title: 'Task moved',
          detail: { id: 1, task_id: 't1', kind: 'move' },
        },
      ],
    });

    render(<DailyJournal />);

    await waitFor(() => {
      expect(screen.getByText('File write approved')).toBeInTheDocument();
    });

    expect(screen.getByText('Approval')).toBeInTheDocument();
    expect(screen.getByText('Cron')).toBeInTheDocument();
    expect(screen.getByText('Kanban')).toBeInTheDocument();
  });

  it('shows empty state when timeline has no rows', async () => {
    getDailyJournalMock.mockResolvedValue(BASE_JOURNAL);

    render(<DailyJournal />);

    await waitFor(() => {
      expect(screen.getByText('No activity on this day')).toBeInTheDocument();
    });
  });
});
