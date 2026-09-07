import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import CronRunItem from '../CronRunItem';
import type { CronRun } from '@/services/cron';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'zh',
}));

describe('CronRunItem', () => {
  const baseRun: CronRun = {
    id: 'run-1',
    job_id: 'job-1',
    started_at: '2026-09-07T12:00:00Z',
    finished_at: '2026-09-07T12:00:05Z',
    duration_ms: 5000,
    status: 'ok',
    output: 'Execution succeeded',
    error: null,
    tokens_used: 1500,
  };

  it('renders ok status correctly', () => {
    render(<CronRunItem run={baseRun} isLast={false} />);
    expect(screen.getByText('runOk')).toBeInTheDocument();
  });

  it('renders circuit_break status and banner correctly when expanded', () => {
    const circuitBreakRun: CronRun = {
      ...baseRun,
      id: 'run-cb-1',
      status: 'circuit_break',
      error: 'RUNAWAY_CIRCUIT_BREAKER: Loop guard triggered in unattended mode',
    };

    render(<CronRunItem run={circuitBreakRun} isLast={false} />);
    expect(screen.getByText('runCircuitBreak')).toBeInTheDocument();

    // Click expand button to view details
    const expandButton = screen.getByRole('button');
    fireEvent.click(expandButton);

    expect(screen.getByText('circuitBreakTitle')).toBeInTheDocument();
    expect(screen.getAllByText(/RUNAWAY_CIRCUIT_BREAKER/).length).toBeGreaterThan(0);
  });

  it('renders default circuitBreakDesc when run.error is null', () => {
    const circuitBreakRunWithoutError: CronRun = {
      ...baseRun,
      id: 'run-cb-2',
      status: 'circuit_break',
      error: null,
    };

    render(<CronRunItem run={circuitBreakRunWithoutError} isLast={false} />);
    const expandButton = screen.getByRole('button');
    fireEvent.click(expandButton);

    expect(screen.getByText('circuitBreakTitle')).toBeInTheDocument();
    expect(screen.getByText('circuitBreakDesc')).toBeInTheDocument();
  });
});
