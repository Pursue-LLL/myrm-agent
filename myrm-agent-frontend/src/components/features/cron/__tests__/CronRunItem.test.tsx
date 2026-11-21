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
    usage_total_tokens: 1500,
  };

  it('renders ok status correctly', () => {
    render(<CronRunItem run={baseRun} isLast={false} />);
    expect(screen.getByText('runOk')).toBeInTheDocument();
  });

  it('explains a circuit break in plain language and never shows the internal error text', () => {
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
    expect(screen.getByText('circuitBreakDesc')).toBeInTheDocument();
    expect(screen.queryByText(/RUNAWAY_CIRCUIT_BREAKER/)).toBeNull();
  });

  it('explains a circuit break when run.error is null', () => {
    const circuitBreakRunWithoutError: CronRun = {
      ...baseRun,
      id: 'run-cb-2',
      status: 'circuit_break',
    };

    render(<CronRunItem run={circuitBreakRunWithoutError} isLast={false} />);
    const expandButton = screen.getByRole('button');
    fireEvent.click(expandButton);

    expect(screen.getByText('circuitBreakTitle')).toBeInTheDocument();
    expect(screen.getByText('circuitBreakDesc')).toBeInTheDocument();
  });

  it.each([
    ['usage_limit', 'skippedUsageLimit'],
    ['budget_blocked', 'skippedBudgetBlocked'],
    ['credit_exhausted', 'skippedCreditExhausted'],
    ['pre-flight-condition', 'skippedPreflight'],
    ['no-content', 'skippedNoContent'],
    ['cooldown_active', 'skippedCooldown'],
    ['outside_active_hours', 'skippedOutsideHours'],
    ['untrusted-workflow', 'skippedUntrustedWorkflow'],
    ['memory_pressure:critical', 'skippedMemoryPressure'],
    ['memory_pressure:emergency', 'skippedMemoryPressure'],
  ])('shows a localized label instead of the raw skip code %s', (code, labelKey) => {
    const skippedRun: CronRun = { ...baseRun, id: 'run-sk-1', status: 'skipped', output: code };

    render(<CronRunItem run={skippedRun} isLast={false} />);

    expect(screen.getByText(labelKey)).toBeInTheDocument();
    expect(screen.queryByText(code)).toBeNull();
  });

  it.each(['made-up-code', 'constructor'])('keeps showing the skip output %s verbatim', (output) => {
    const skippedRun: CronRun = { ...baseRun, id: 'run-sk-2', status: 'skipped', output };

    render(<CronRunItem run={skippedRun} isLast={false} />);

    expect(screen.getByText(output)).toBeInTheDocument();
  });

  it.each([
    ['event', 'triggerSourceEvent'],
    ['webhook', 'triggerSourceWebhook'],
    ['system_event', 'triggerSourceSystem'],
    ['manual', 'triggerSourceManual'],
    ['recovery', 'triggerSourceRecovery'],
    ['shutdown', 'triggerSourceShutdown'],
  ])('names the source %s of a run with its label', (source, labelKey) => {
    render(<CronRunItem run={{ ...baseRun, trigger_source: source }} isLast={false} />);

    expect(screen.getByText(labelKey)).toBeInTheDocument();
    expect(screen.queryByText(source)).toBeNull();
  });

  it('shows no source badge for a run its own schedule started', () => {
    render(<CronRunItem run={{ ...baseRun, trigger_source: 'cron' }} isLast={false} />);

    expect(screen.queryByText('triggerSourceCron')).toBeNull();
    expect(screen.queryByText('cron')).toBeNull();
  });

  it('keeps showing a source it has no label for verbatim', () => {
    render(<CronRunItem run={{ ...baseRun, trigger_source: 'made-up-source' }} isLast={false} />);

    expect(screen.getByText('made-up-source')).toBeInTheDocument();
  });

  it('does not turn the output of a run that is not skipped into a label', () => {
    const okRun: CronRun = { ...baseRun, id: 'run-ok-2', status: 'ok', output: 'no-content' };

    render(<CronRunItem run={okRun} isLast={false} />);

    expect(screen.getByText('no-content')).toBeInTheDocument();
    expect(screen.queryByText('skippedNoContent')).toBeNull();
  });

  it('labels the token counts and lists the steps in the expanded view', () => {
    const detailedRun: CronRun = {
      ...baseRun,
      id: 'run-detail-1',
      usage_input_tokens: 1200,
      usage_output_tokens: 300,
      metadata: { progressSteps: [{ tool_name: 'web_search' }] },
    };

    render(<CronRunItem run={detailedRun} isLast={false} />);
    fireEvent.click(screen.getByRole('button'));

    expect(screen.getByText('statInput: 1.2k')).toBeInTheDocument();
    expect(screen.getByText('statOutput: 300')).toBeInTheDocument();
    expect(screen.getByText('web_search')).toBeInTheDocument();
  });

  it('names a failed delivery by its localized category and never by the internal code', () => {
    const failedDelivery: CronRun = {
      ...baseRun,
      id: 'run-del-1',
      delivery_error: 'ReadTimeout',
      metadata: {
        connector_failure: { category: 'timeout', target: 'https://hooks.example.com/a' },
      },
    };

    render(<CronRunItem run={failedDelivery} isLast={false} />);
    fireEvent.click(screen.getByRole('button'));

    expect(screen.getByText('connectorCategoryTimeout')).toBeInTheDocument();
    expect(screen.getByText('https://hooks.example.com/a')).toBeInTheDocument();
    expect(screen.queryByText('timeout')).toBeNull();
    // The run row says what went wrong; what to do about it is for the badge's popover.
    expect(screen.queryByText('connectorCategoryTimeoutHint')).toBeNull();
  });

  describe('job name', () => {
    it('names the job a run belongs to when asked to', () => {
      render(<CronRunItem run={{ ...baseRun, job_name: 'Daily digest' }} isLast={false} showJobName />);

      expect(screen.getByText('Daily digest')).toBeInTheDocument();
    });

    it('shows the heartbeat by its title, not by its reserved stored name', () => {
      render(<CronRunItem run={{ ...baseRun, job_name: '__heartbeat__' }} isLast={false} showJobName />);

      expect(screen.getByText('title')).toBeInTheDocument();
      expect(screen.queryByText('__heartbeat__')).toBeNull();
    });

    it('leaves the name out when not asked to show it', () => {
      render(<CronRunItem run={{ ...baseRun, job_name: 'Daily digest' }} isLast={false} />);

      expect(screen.queryByText('Daily digest')).toBeNull();
    });
  });
});
