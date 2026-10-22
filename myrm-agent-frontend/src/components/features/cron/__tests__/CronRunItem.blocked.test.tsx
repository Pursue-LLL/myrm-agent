import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import CronRunItem from '../CronRunItem';
import type { CronRun } from '@/services/cron';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const baseRun: CronRun = {
  id: 'run-1',
  job_id: 'job-1',
  started_at: '2026-09-07T12:00:00Z',
  finished_at: '2026-09-07T12:00:05Z',
  duration_ms: 5000,
  status: 'ok',
  output: 'Execution succeeded',
};

const blockedMetadata: NonNullable<CronRun['metadata']> = {
  blockedCount: 3,
  blockedActions: [{ tool: 'file_write_tool', reason: 'Capability not granted: file_write', count: 3 }],
};

describe('CronRunItem blocked actions', () => {
  it('flags a finished run that had actions stopped, from the structured metadata', () => {
    render(<CronRunItem run={{ ...baseRun, metadata: blockedMetadata }} isLast={false} />);

    expect(screen.getByText('runOk')).toBeInTheDocument();
    expect(screen.getByText('blockedBadge')).toBeInTheDocument();
  });

  it('explains the stopped actions once the run is expanded', () => {
    render(<CronRunItem run={{ ...baseRun, metadata: blockedMetadata }} isLast={false} />);
    expect(screen.queryByText('blockedHint')).toBeNull();

    fireEvent.click(screen.getByRole('button'));

    expect(screen.getByText('blockedTitle')).toBeInTheDocument();
    expect(screen.getByText('Capability not granted: file_write')).toBeInTheDocument();
    expect(screen.getByText('blockedHint')).toBeInTheDocument();
  });

  it('does not infer a denial from the wording of an error the run recorded no blocked actions for', () => {
    const failedRun: CronRun = {
      ...baseRun,
      status: 'error',
      output: undefined,
      error: 'Tool execution denied by security policy: cron fail-closed policy',
    };
    render(<CronRunItem run={failedRun} isLast={false} />);

    fireEvent.click(screen.getByRole('button'));

    expect(screen.queryByText('blockedBadge')).toBeNull();
    expect(screen.queryByText('blockedHint')).toBeNull();
  });

  it('offers the details of a run whose only content is the stopped actions', () => {
    const noContentRun: CronRun = { ...baseRun, output: undefined };

    const { unmount } = render(<CronRunItem run={noContentRun} isLast={false} />);
    expect(screen.queryByRole('button')).toBeNull();
    unmount();

    render(<CronRunItem run={{ ...noContentRun, metadata: blockedMetadata }} isLast={false} />);
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('blockedTitle')).toBeInTheDocument();
  });
});
