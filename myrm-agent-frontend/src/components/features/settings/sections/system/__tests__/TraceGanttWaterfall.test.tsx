/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TraceGanttWaterfall from '../TraceGanttWaterfall';
import type { TracePerformanceSummary } from '@/services/statistics';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params?.tokens) return `Cached: ${params.tokens} Tokens`;
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

describe('TraceGanttWaterfall Component', () => {
  const mockPerformance: TracePerformanceSummary = {
    llm_duration_ms: 1200,
    tool_duration_ms: 800,
    total_prompt_tokens: 10000,
    total_completion_tokens: 1200,
    total_cache_read_tokens: 8500,
    prompt_cache_hit_ratio: 0.85,
    gantt_spans: [
      {
        type: 'llm',
        label: 'deepseek-chat',
        start_time: 1.0,
        end_time: 2.2,
        duration_ms: 1200,
        ttft_ms: 280,
        status: 'success',
      },
      {
        type: 'tool',
        label: 'web_search',
        start_time: 2.2,
        end_time: 3.0,
        duration_ms: 800,
        status: 'success',
      },
    ],
  };

  it('renders gantt waterfall header and timing ratios', () => {
    render(<TraceGanttWaterfall performance={mockPerformance} totalDurationMs={2000} />);

    expect(screen.getByText('ganttWaterfall')).toBeInTheDocument();
    expect(screen.getByText('privacyMode')).toBeInTheDocument();
    expect(screen.getByText(/llmTime \(60%\)/)).toBeInTheDocument();
    expect(screen.getByText(/toolTime \(40%\)/)).toBeInTheDocument();
  });

  it('renders prompt cache hit percentage and cached tokens', () => {
    render(<TraceGanttWaterfall performance={mockPerformance} totalDurationMs={2000} />);

    expect(screen.getByText('cacheHitRate')).toBeInTheDocument();
    expect(screen.getByText('85%')).toBeInTheDocument();
    expect(screen.getByText('Cached: 8,500 Tokens')).toBeInTheDocument();
  });

  it('renders spans and allows selecting a span to inspect details', async () => {
    render(<TraceGanttWaterfall performance={mockPerformance} totalDurationMs={2000} />);

    expect(screen.getByText('deepseek-chat')).toBeInTheDocument();
    expect(screen.getByText('web_search')).toBeInTheDocument();

    const spanItem = screen.getByText('deepseek-chat');
    await userEvent.click(spanItem);

    // Selected span details should appear
    expect(screen.getByText(/TTFT: 280ms/)).toBeInTheDocument();
  });

  it('toggles privacy mode and masks labels', async () => {
    render(<TraceGanttWaterfall performance={mockPerformance} totalDurationMs={2000} />);

    expect(screen.getByText('deepseek-chat')).toBeInTheDocument();

    const privacyBtn = screen.getByRole('button', { name: /privacyMode/ });
    await userEvent.click(privacyBtn);

    // Labels should be masked to LLM and Tool
    expect(screen.queryByText('deepseek-chat')).not.toBeInTheDocument();
    expect(screen.getByText('LLM')).toBeInTheDocument();
    expect(screen.getByText('Tool')).toBeInTheDocument();
  });

  it('handles empty spans gracefully without crashing', () => {
    render(
      <TraceGanttWaterfall
        performance={{
          llm_duration_ms: 0,
          tool_duration_ms: 0,
          total_prompt_tokens: 0,
          total_completion_tokens: 0,
          total_cache_read_tokens: 0,
          prompt_cache_hit_ratio: 0,
          gantt_spans: [],
        }}
        totalDurationMs={0}
      />
    );

    expect(screen.getByTestId('trace-gantt-waterfall')).toBeInTheDocument();
    expect(screen.getByText(/Execution Waterfall \(0 spans\)/)).toBeInTheDocument();
  });
});
