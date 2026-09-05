/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TraceGanttWaterfall from '../TraceGanttWaterfall';
import type { TracePerformanceSummary } from '@/services/statistics';

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
        start_time: 1000.0,
        end_time: 1001.2,
        duration_ms: 1200,
        ttft_ms: 280,
        status: 'success',
      },
      {
        type: 'tool',
        label: 'web_search',
        start_time: 1001.2,
        end_time: 1002.0,
        duration_ms: 800,
        status: 'success',
      },
    ],
  };

  it('renders LLM and Tool timing breakdown correctly', () => {
    render(<TraceGanttWaterfall performance={mockPerformance} totalDurationMs={2000} />);

    expect(screen.getByTestId('trace-gantt-waterfall')).toBeInTheDocument();
    expect(screen.getByText(/LLM 60%/)).toBeInTheDocument();
    expect(screen.getByText(/Tool 40%/)).toBeInTheDocument();
  });

  it('renders prompt cache hit badge with percentage and token counts', () => {
    render(<TraceGanttWaterfall performance={mockPerformance} totalDurationMs={2000} />);

    const badge = screen.getByTestId('prompt-cache-badge');
    expect(badge).toBeInTheDocument();
    expect(screen.getByText(/Prompt Cache: 85%/)).toBeInTheDocument();
    expect(screen.getByText(/\(8,500 \/ 10,000\)/)).toBeInTheDocument();
  });

  it('renders waterfall spans for LLM and tool calls', () => {
    render(<TraceGanttWaterfall performance={mockPerformance} totalDurationMs={2000} />);

    expect(screen.getByText('deepseek-chat')).toBeInTheDocument();
    expect(screen.getByText('web_search')).toBeInTheDocument();
    expect(screen.getByText(/Execution Waterfall \(2 spans\)/)).toBeInTheDocument();
  });

  it('supports expanding and collapsing when spans exceed threshold', async () => {
    const manySpansPerformance: TracePerformanceSummary = {
      ...mockPerformance,
      gantt_spans: Array.from({ length: 8 }, (_, i) => ({
        type: i % 2 === 0 ? 'llm' : 'tool',
        label: `step-${i + 1}`,
        start_time: 1000 + i * 0.5,
        end_time: 1000 + (i + 1) * 0.5,
        duration_ms: 500,
        status: 'success',
      })),
    };

    render(<TraceGanttWaterfall performance={manySpansPerformance} totalDurationMs={4000} />);

    expect(screen.getByText(/Execution Waterfall \(8 spans\)/)).toBeInTheDocument();
    // Default displays up to 6 spans
    expect(screen.getByText('step-1')).toBeInTheDocument();
    expect(screen.getByText('step-6')).toBeInTheDocument();
    expect(screen.queryByText('step-7')).not.toBeInTheDocument();

    const expandBtn = screen.getByRole('button', { name: /Show all 8/ });
    await userEvent.click(expandBtn);

    // After expand, all spans visible
    expect(screen.getByText('step-7')).toBeInTheDocument();
    expect(screen.getByText('step-8')).toBeInTheDocument();

    const collapseBtn = screen.getByRole('button', { name: /Collapse/ });
    await userEvent.click(collapseBtn);

    expect(screen.queryByText('step-7')).not.toBeInTheDocument();
  });

  it('handles empty spans gracefully without crashing', () => {
    const emptyPerformance: TracePerformanceSummary = {
      llm_duration_ms: 0,
      tool_duration_ms: 0,
      total_prompt_tokens: 0,
      total_completion_tokens: 0,
      total_cache_read_tokens: 0,
      prompt_cache_hit_ratio: 0,
      gantt_spans: [],
    };

    render(<TraceGanttWaterfall performance={emptyPerformance} totalDurationMs={0} />);

    expect(screen.getByTestId('trace-gantt-waterfall')).toBeInTheDocument();
    expect(screen.queryByTestId('prompt-cache-badge')).not.toBeInTheDocument();
  });
});
