/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SessionAnalytics } from '@/services/statistics';

import SessionAnalyticsDialog from '../SessionAnalyticsDialog';

vi.mock('next-intl', () => {
  const modeKeys: Record<string, string> = {
    fast: 'Fast Search',
    agent: 'AI Agent',
  };
  return {
    useTranslations: (namespace?: string) => {
      if (namespace === 'mode') {
        const t = (key: string): string => modeKeys[key] ?? key;
        t.has = (key: string): boolean => key in modeKeys;
        return t;
      }
      const t = (key: string): string => key;
      t.has = (key: string): boolean => true;
      return t;
    },
  };
});

vi.mock('@/services/statistics', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/statistics')>();
  return {
    ...actual,
    getSessionAnalytics: vi.fn(),
  };
});

vi.mock('../SessionContextHealthPanel', () => ({
  default: () => <div data-testid="context-health" />,
}));

vi.mock('../ExecutionTraceTimeline', () => ({
  default: () => <div data-testid="trace-timeline" />,
}));

import { getSessionAnalytics } from '@/services/statistics';

const getSessionAnalyticsMock = vi.mocked(getSessionAnalytics);

const BASE_ANALYTICS: SessionAnalytics = {
  session_id: 's1',
  title: 'Test Session',
  action_mode: 'fast',
  created_at: null,
  duration_ms: 60000,
  message_count: 2,
  user_messages: 1,
  assistant_messages: 1,
  calls: 3,
  inputTokens: 100,
  outputTokens: 50,
  cachedTokens: 0,
  reasoningTokens: 0,
  citationTokens: 0,
  totalTokens: 150,
  costUsd: 0.01,
  cacheHitRate: 0.5,
  modelBreakdown: {},
  tool_breakdown: [],
  events_timeline: [],
  task_metrics: {},
  context_health: {} as SessionAnalytics['context_health'],
};

describe('SessionAnalyticsDialog', () => {
  beforeEach(() => {
    getSessionAnalyticsMock.mockResolvedValue(BASE_ANALYTICS);
  });

  it('renders LLM breakdown when data is present', async () => {
    getSessionAnalyticsMock.mockResolvedValue({
      ...BASE_ANALYTICS,
      llm_breakdown: [
        { model_name: 'gpt-4o', call_count: 3, total_duration_ms: 2400 },
        { model_name: 'claude-sonnet', call_count: 1, total_duration_ms: 500 },
      ],
    });

    render(<SessionAnalyticsDialog sessionId="s1" onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('llmBreakdown')).toBeInTheDocument());
    expect(screen.getByText('gpt-4o')).toBeInTheDocument();
    expect(screen.getByText('claude-sonnet')).toBeInTheDocument();
    expect(screen.getAllByText('3 calls').length).toBeGreaterThan(0);
    expect(screen.getByText('2400ms total')).toBeInTheDocument();
  });

  it('renders duration stat card', async () => {
    render(<SessionAnalyticsDialog sessionId="s1" onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('duration')).toBeInTheDocument());
    expect(screen.getByText('1m 0s')).toBeInTheDocument();
  });

  it('renders tool breakdown alongside LLM breakdown', async () => {
    getSessionAnalyticsMock.mockResolvedValue({
      ...BASE_ANALYTICS,
      llm_breakdown: [{ model_name: 'gpt-4o', call_count: 2, total_duration_ms: 1200 }],
      tool_breakdown: [{ tool_name: 'bash', call_count: 4, total_duration_ms: 800 }],
    });

    render(<SessionAnalyticsDialog sessionId="s1" onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('llmBreakdown')).toBeInTheDocument());
    expect(screen.getByText('gpt-4o')).toBeInTheDocument();
    expect(screen.getByText('toolBreakdown')).toBeInTheDocument();
    expect(screen.getByText('bash')).toBeInTheDocument();
  });

  it('renders copy markdown and download csv buttons for audit ledger', async () => {
    render(<SessionAnalyticsDialog sessionId="s1" onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('copyMarkdown')).toBeInTheDocument());
    expect(screen.getByText('downloadCsv')).toBeInTheDocument();
  });

  it('renders response speed summary when streamTtft is present', async () => {
    getSessionAnalyticsMock.mockResolvedValue({
      ...BASE_ANALYTICS,
      streamTtft: { sampleCount: 5, avgMs: 800, p95Ms: 1500 },
    });

    render(<SessionAnalyticsDialog sessionId="s1" onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('responseSpeed')).toBeInTheDocument());
    expect(screen.getByText('800')).toBeInTheDocument();
    expect(screen.getByText('1500')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('hides response speed section when streamTtft is absent', async () => {
    render(<SessionAnalyticsDialog sessionId="s1" onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('duration')).toBeInTheDocument());
    expect(screen.queryByText('responseSpeed')).not.toBeInTheDocument();
  });

  it('localizes known action mode via mode namespace', async () => {
    getSessionAnalyticsMock.mockResolvedValue({ ...BASE_ANALYTICS, action_mode: 'agent' });

    render(<SessionAnalyticsDialog sessionId="s1" onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText(/AI Agent/)).toBeInTheDocument());
  });

  it('falls back to raw action mode value for unknown modes', async () => {
    getSessionAnalyticsMock.mockResolvedValue({ ...BASE_ANALYTICS, action_mode: 'future_custom_mode' });

    render(<SessionAnalyticsDialog sessionId="s1" onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText(/future_custom_mode/)).toBeInTheDocument());
  });

  it('shows the copied state after the markdown ledger is written to the clipboard', async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });

    render(<SessionAnalyticsDialog sessionId="s1" onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText('copyMarkdown'));

    expect(await screen.findByText('copied')).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('Audit Ledger'));
  });

  it('marks blocked and denied security audit kinds with the destructive text token', async () => {
    getSessionAnalyticsMock.mockResolvedValue({
      ...BASE_ANALYTICS,
      security_audit: { total: 8, breakdown: { TOOL_BLOCKED: 2, NETWORK_DENY: 1, TAINT_FLAG: 5 } },
    });

    render(<SessionAnalyticsDialog sessionId="s1" onClose={vi.fn()} />);

    expect(await screen.findByText('TOOL_BLOCKED')).toHaveClass('text-destructive-text');
    expect(screen.getByText('NETWORK_DENY')).toHaveClass('text-destructive-text');
    expect(screen.getByText('TAINT_FLAG')).not.toHaveClass('text-destructive-text');
  });

  it('renders the load error with the destructive text token', async () => {
    getSessionAnalyticsMock.mockRejectedValue(new Error('boom'));

    render(<SessionAnalyticsDialog sessionId="s1" onClose={vi.fn()} />);

    expect((await screen.findByText('boom')).parentElement).toHaveClass('text-destructive-text');
  });
});
