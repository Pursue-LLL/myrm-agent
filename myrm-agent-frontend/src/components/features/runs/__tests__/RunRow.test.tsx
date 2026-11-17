/** @vitest-environment jsdom */
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

// The real timeline renders replay / export / tool-call buttons; one button stands in for all of them.
vi.mock('@/components/features/settings/sections/system/ExecutionTraceTimeline', () => ({
  default: () => (
    <div data-testid="mock-trace-timeline">
      <button type="button">replay</button>
    </div>
  ),
}));

import type { UnifiedRun } from '@/services/runs';
import { RunRow } from '../RunRow';

const t = stableT as unknown as ComponentProps<typeof RunRow>['t'];

function makeRun(overrides: Partial<UnifiedRun> = {}): UnifiedRun {
  return {
    id: 'cron:job-1:run-1',
    source: 'cron',
    status: 'ok',
    title: 'Daily AI digest',
    started_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    duration_ms: 1200,
    error: null,
    summary: 'Done',
    output: null,
    metadata: null,
    agent_id: 'agent-1',
    job_id: 'job-1',
    task_id: null,
    has_execution_steps: false,
    stop_reason: null,
    ...overrides,
  };
}

function renderRow(run: UnifiedRun) {
  render(<RunRow run={run} t={t} />);
}

function header(title: string | RegExp) {
  return screen.getByRole('button', { name: title });
}

describe('RunRow', () => {
  it('renders no button for a run that has nothing to expand', () => {
    renderRow(makeRun());

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('toggles from its header and tells assistive tech which region it controls', async () => {
    renderRow(makeRun({ output: 'digest output' }));

    const toggle = header(/Daily AI digest/);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).not.toHaveAttribute('aria-controls');

    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const region = document.getElementById(toggle.getAttribute('aria-controls') ?? '');
    expect(region).toContainElement(screen.getByText('digest output'));

    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('digest output')).not.toBeInTheDocument();
  });

  it('keeps the row open when the expanded output is clicked', async () => {
    renderRow(makeRun({ output: 'digest output' }));

    await userEvent.click(header(/Daily AI digest/));
    await userEvent.click(screen.getByText('digest output'));

    expect(screen.getByText('digest output')).toBeInTheDocument();
    expect(header(/Daily AI digest/)).toHaveAttribute('aria-expanded', 'true');
  });

  it('keeps the row open when a control inside the execution trace is clicked', async () => {
    renderRow(makeRun({ source: 'kanban', title: 'Summarize repo', task_id: 'task-1', job_id: null }));

    await userEvent.click(header(/Summarize repo/));
    await userEvent.click(await screen.findByRole('button', { name: 'replay' }));

    expect(screen.getByTestId('mock-trace-timeline')).toBeInTheDocument();
    expect(header(/Summarize repo/)).toHaveAttribute('aria-expanded', 'true');
  });

  it('opens and closes from the keyboard with Enter and Space', async () => {
    renderRow(makeRun({ output: 'digest output' }));

    const toggle = header(/Daily AI digest/);
    toggle.focus();

    await userEvent.keyboard('{Enter}');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    await userEvent.keyboard(' ');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('shows when the run started through the shared locale-aware formatter', () => {
    renderRow(makeRun({ started_at: new Date(Date.now() - 5 * 60_000).toISOString() }));

    expect(screen.getByText('5 minutes ago')).toBeInTheDocument();
  });

  it('labels a progress step only by what the run recorded for it', async () => {
    renderRow(
      makeRun({
        has_execution_steps: true,
        metadata: { progressSteps: [{ error: 'boom' }, { tool_name: 'web_search' }] },
      }),
    );

    await userEvent.click(header(/Daily AI digest/));

    expect(screen.getByText('web_search')).toBeInTheDocument();
    expect(screen.queryByText(/^step \d+$/)).not.toBeInTheDocument();
  });
});
