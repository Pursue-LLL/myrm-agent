import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import WbBenchSources from '../WbBenchSources';

interface ReportItem {
  timestamp?: number;
  total_cases?: number;
  pass_count?: number;
  skip_count?: number;
  pass_rate?: number;
  avg_pass_rate?: number | null;
  manifest?: {
    task_set_id?: string;
  };
}

function sourcesPayload() {
  return {
    status: 'success',
    sources: [
      {
        id: 'office',
        name: 'Office',
        task_count: 50,
        approx_size_mb: 12,
        is_downloaded: true,
        local_size_bytes: 12 * 1024 * 1024,
        scoring: 'composite',
      },
    ],
  };
}

function renderSources(history: ReportItem[]) {
  const props = {
    running: false,
    history,
    onRun: vi.fn(),
    onDownload: vi.fn(),
    onMemoryAb: vi.fn(),
    refreshToken: 0,
    downloadingSubsetId: null,
    downloadProgress: null,
  };
  return render(<WbBenchSources {...props} />);
}

describe('WbBenchSources', () => {
  it('renders dataset cards and the downloaded badge', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(sourcesPayload()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    renderSources([]);

    await waitFor(() => expect(screen.getByText('Office')).toBeInTheDocument());
    // The badge and the download button both read "downloaded" on a downloaded card.
    expect(screen.getAllByText('downloaded').length).toBeGreaterThan(0);
    expect(screen.getByText('scoringComposite')).toBeInTheDocument();
  });

  it('shows the avg_pass_rate (test pass rate) badge when a scored report exists', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(sourcesPayload()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const history: ReportItem[] = [
      {
        timestamp: 1750000000,
        total_cases: 10,
        pass_count: 8,
        skip_count: 0,
        avg_pass_rate: 0.75,
        manifest: { task_set_id: 'wb-bench-office' },
      },
    ];

    renderSources(history);

    await waitFor(() => expect(screen.getByText('Office')).toBeInTheDocument());
    expect(screen.getByText('testPassRate')).toBeInTheDocument();
    // avg_pass_rate 0.75 → 75%
    expect(screen.getByText('75%')).toBeInTheDocument();
  });

  it('renders pending-scoring state when a report exists but was skipped entirely', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(sourcesPayload()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const history: ReportItem[] = [
      {
        timestamp: 1750000000,
        total_cases: 10,
        pass_count: 0,
        skip_count: 10,
        avg_pass_rate: null,
        manifest: { task_set_id: 'wb-bench-office' },
      },
    ];

    renderSources(history);

    await waitFor(() => expect(screen.getByText('Office')).toBeInTheDocument());
    // isScored requires skip_count < total_cases → here fully skipped, so pending.
    expect(screen.getByText('pendingScoring')).toBeInTheDocument();
    expect(screen.queryByText('testPassRate')).not.toBeInTheDocument();
  });

  it('does not show a report section at all when no matching report exists', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(sourcesPayload()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    // A report for a different subset must not leak into this card.
    const history: ReportItem[] = [
      {
        timestamp: 1750000000,
        total_cases: 10,
        pass_count: 8,
        skip_count: 0,
        avg_pass_rate: 0.75,
        manifest: { task_set_id: 'wb-bench-code' },
      },
    ];

    renderSources(history);

    await waitFor(() => expect(screen.getByText('Office')).toBeInTheDocument());
    expect(screen.getByText('noReport')).toBeInTheDocument();
    expect(screen.queryByText('testPassRate')).not.toBeInTheDocument();
  });
});
