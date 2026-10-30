import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import CronRunSteps from '../CronRunSteps';
import type { CronRun } from '@/services/cron';

const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const toastSuccess = vi.hoisted(() => vi.fn());
vi.mock('sonner', () => ({ toast: { success: toastSuccess } }));

const baseRun: CronRun = {
  id: 'run-1',
  job_id: 'job-1',
  started_at: '2026-09-07T12:00:00Z',
  finished_at: '2026-09-07T12:00:05Z',
  duration_ms: 5000,
  status: 'ok',
  output: 'done',
  usage_input_tokens: 1200,
  usage_output_tokens: 300,
  usage_total_tokens: 1500,
};

function runWithSteps(progressSteps: NonNullable<CronRun['metadata']>['progressSteps']): CronRun {
  return { ...baseRun, metadata: { progressSteps } };
}

describe('CronRunSteps', () => {
  const writeText = vi.fn();

  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it.each([undefined, []])('renders nothing for a run with steps %j', (progressSteps) => {
    const { container } = render(<CronRunSteps run={runWithSteps(progressSteps)} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('names each step by its tool, then its step key, then its position', () => {
    render(<CronRunSteps run={runWithSteps([{ tool_name: 'web_search' }, { step_key: 'summarize' }, {}])} />);

    expect(screen.getByText('executionSteps (3)')).toBeInTheDocument();
    expect(screen.getByText('web_search')).toBeInTheDocument();
    expect(screen.getByText('summarize')).toBeInTheDocument();
    expect(screen.getByText('stepFallback:{"index":3}')).toBeInTheDocument();
  });

  it('shows the error of a failed step', () => {
    render(<CronRunSteps run={runWithSteps([{ tool_name: 'shell', error: 'exit code 2' }])} />);

    expect(screen.getByText('exit code 2')).toHaveAttribute('title', 'exit code 2');
  });

  it('copies the whole audit trace of the run and says so', () => {
    const steps = [{ tool_name: 'web_search' }];
    render(<CronRunSteps run={{ ...runWithSteps(steps), model: 'openai/gpt-4o', trigger_source: 'manual' }} />);

    fireEvent.click(screen.getByRole('button', { name: 'copyAuditTrace' }));

    expect(JSON.parse(writeText.mock.calls[0][0])).toMatchObject({
      run_id: 'run-1',
      job_id: 'job-1',
      status: 'ok',
      trigger_source: 'manual',
      model: 'openai/gpt-4o',
      usage: { input: 1200, output: 300, total: 1500 },
      steps,
      output: 'done',
    });
    expect(toastSuccess).toHaveBeenCalledWith('traceCopied');
  });

  it('falls back to cron when the run has no trigger source', () => {
    render(<CronRunSteps run={runWithSteps([{ tool_name: 'web_search' }])} />);

    fireEvent.click(screen.getByRole('button', { name: 'copyAuditTrace' }));

    expect(JSON.parse(writeText.mock.calls[0][0]).trigger_source).toBe('cron');
  });
});
