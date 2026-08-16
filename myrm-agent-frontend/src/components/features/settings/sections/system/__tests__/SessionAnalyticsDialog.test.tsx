/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SessionAnalytics } from '@/services/statistics';

import SessionAnalyticsDialog from '../SessionAnalyticsDialog';

vi.mock('next-intl', () => {
  const modeKeys: Record<string, string> = {
    fast: 'Fast Search',
    agent: 'AI Agent',
    deep_research: 'Deep Research',
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
    getSessionAnalyticsMock.mockResolvedValue({ ...BASE_ANALYTICS, action_mode: 'deep_research' });

    render(<SessionAnalyticsDialog sessionId="s1" onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText(/Deep Research/)).toBeInTheDocument());
  });

  it('falls back to raw action mode value for unknown modes', async () => {
    getSessionAnalyticsMock.mockResolvedValue({ ...BASE_ANALYTICS, action_mode: 'future_custom_mode' });

    render(<SessionAnalyticsDialog sessionId="s1" onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText(/future_custom_mode/)).toBeInTheDocument());
  });
});
