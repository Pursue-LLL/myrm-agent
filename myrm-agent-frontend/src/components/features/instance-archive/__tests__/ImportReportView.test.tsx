/** @vitest-environment jsdom */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ImportReport } from '@/services/instanceArchive';
import { ImportReportView } from '../ImportReportView';

const stableT = (key: string, params?: Record<string, unknown>) =>
  params ? `${key}:${Object.values(params).join('|')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const report = (overrides: Partial<ImportReport> = {}): ImportReport => ({
  session_id: 's1',
  created_at: '2026-09-13T12:00:00Z',
  counts: { chats: 12, messages: 340 },
  current_counts: {},
  executable: {},
  reentry: [],
  paused_jobs: 0,
  missing_paths: 0,
  unreadable_count: 0,
  identity_dropped: false,
  config_key_carried: false,
  ...overrides,
});

const renderReview = (value: ImportReport) =>
  render(<ImportReportView report={value} acknowledged={false} onAcknowledgedChange={vi.fn()} />);

describe('ImportReportView', () => {
  it('shows when the backup was made and sets each count beside what the app holds now', () => {
    renderReview(
      report({
        counts: { chats: 12, messages: 340, cron_jobs: 2 },
        current_counts: { chats: 20, messages: 900, cron_jobs: 2 },
      }),
    );

    expect(screen.getByText(/^madeAt:.*2026/)).toBeInTheDocument();
    expect(screen.getByText('counts.cron_jobs')).toBeInTheDocument();
    expect(screen.getByText('nowCount:20')).toBeInTheDocument();
    expect(screen.getByText('nowCount:900')).toBeInTheDocument();
    expect(screen.getByText('losesHistory')).toBeInTheDocument();
  });

  it('stays quiet about history when the backup holds as much as the app does now', () => {
    renderReview(report({ current_counts: { chats: 12, messages: 40 } }));

    expect(screen.getByText('nowCount:12')).toBeInTheDocument();
    expect(screen.queryByText('losesHistory')).not.toBeInTheDocument();
  });

  it('shows no comparison when the running app could not be read', () => {
    renderReview(report());

    expect(screen.getByText('counts.chats')).toBeInTheDocument();
    expect(screen.queryByText(/^nowCount/)).not.toBeInTheDocument();
    expect(screen.queryByText('losesHistory')).not.toBeInTheDocument();
  });

  it('warns, with the number, that restoring an incomplete backup also removes what the backup lacks', () => {
    renderReview(report({ unreadable_count: 3 }));

    expect(screen.getByText('incomplete:3')).toBeInTheDocument();
  });

  it('stays quiet about completeness when the backup lacks nothing', () => {
    renderReview(report());

    expect(screen.queryByText(/^incomplete/)).not.toBeInTheDocument();
  });

  it('leaves the date out rather than showing a broken one', () => {
    renderReview(report({ created_at: 'not-a-date' }));

    expect(screen.queryByText(/^madeAt/)).not.toBeInTheDocument();
  });
});
