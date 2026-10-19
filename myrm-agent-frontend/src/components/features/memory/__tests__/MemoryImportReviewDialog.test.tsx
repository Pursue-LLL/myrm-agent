/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../dialogs/MemoryImportReviewDialog::MemoryImportReviewDialog (POS: 记忆导入审查弹窗)
 *
 * [OUTPUT]
 * MemoryImportReviewDialog 单测：有界解析样例、告警文案与来源标签回退。
 *
 * [POS]
 * 记忆导入审查弹窗回归测试。断言服务端样例可见、告警码不裸泄漏、未知导入源不显示裸标识符。
 */
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { MemoryImportDryRunResult } from '@/services/memory/archive';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

import { MemoryImportReviewDialog } from '../dialogs/MemoryImportReviewDialog';

const makeDryRun = (overrides: Partial<MemoryImportDryRunResult> = {}): MemoryImportDryRunResult => ({
  summary: {
    source: 'pasted_memory',
    version: '1',
    total_items: 3,
    mapped_items: 3,
    unmapped_items: 0,
    status: 'ready',
  },
  mappings: [
    {
      source_bucket: 'pasted_entries',
      target_bucket: 'semantic',
      status: 'mapped',
      item_count: 2,
      imported_count: 2,
      unmapped_count: 0,
      reason: '',
    },
  ],
  warnings: [],
  normalized_data: {
    semantic: [{ content: 'Prefers dark mode in every editor', created_at: '2026-01-02T00:00:00Z' }],
  },
  ...overrides,
});

const renderDialog = (dryRun: MemoryImportDryRunResult | null, onConfirm = vi.fn()) => {
  render(
    <MemoryImportReviewDialog
      open
      dryRun={dryRun}
      expiresAt="2026-01-02T01:00:00Z"
      importing={false}
      onOpenChange={() => undefined}
      onConfirm={onConfirm}
    />,
  );
  return onConfirm;
};

describe('MemoryImportReviewDialog', () => {
  afterEach(cleanup);

  it('shows the bounded parsed sample with bucket labels and entry copy', () => {
    renderDialog(makeDryRun());

    expect(screen.getByText('Parsed sample (1)')).toBeInTheDocument();
    expect(screen.getByText('Showing 1 of 3 parsed entries.')).toBeInTheDocument();
    expect(screen.getByText('Knowledge')).toBeInTheDocument();
    expect(screen.getByText('Prefers dark mode in every editor')).toBeInTheDocument();
    expect(screen.getByText('Pasted memory')).toBeInTheDocument();
    expect(screen.getByText('Jan 2, 2026')).toBeInTheDocument();
    expect(screen.queryByText('2026-01-02T00:00:00Z')).toBeNull();
  });

  it('states that everything shown is imported when the sample is complete', () => {
    renderDialog(
      makeDryRun({
        summary: {
          source: 'pasted_memory',
          version: '1',
          total_items: 1,
          mapped_items: 1,
          unmapped_items: 0,
          status: 'ready',
        },
      }),
    );

    expect(
      screen.getByText('Only a sample is shown. Importing brings in everything listed above.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Showing \d+ of \d+ parsed entries/)).toBeNull();
  });

  it('renders shared warning copy instead of raw warning codes', () => {
    renderDialog(makeDryRun({ warnings: ['pasted_entries_over_limit', 'agentmemory_graph_skipped'] }));

    expect(
      screen.getByText('One paste contained too many entries; split the export into several pastes.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Knowledge-graph links are not imported yet; supported relationship details stay attached to each memory.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('pasted_entries_over_limit')).toBeNull();
  });

  it('falls back to the unknown source label for sources it has no copy for', () => {
    renderDialog(
      makeDryRun({
        summary: {
          source: 'brand_new_export' as MemoryImportDryRunResult['summary']['source'],
          version: '1',
          total_items: 1,
          mapped_items: 0,
          unmapped_items: 1,
          status: 'missing',
        },
      }),
    );

    expect(screen.getByText('Unknown source')).toBeInTheDocument();
    expect(screen.queryByText('brand_new_export')).toBeNull();
  });

  it('confirms the reviewed payload', async () => {
    const user = userEvent.setup();
    const onConfirm = renderDialog(makeDryRun());

    await user.click(screen.getByRole('button', { name: 'Import' }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
