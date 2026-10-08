/** @vitest-environment jsdom */

/**
 * Test suite verifying Item 144 CodebaseMemoryLargeDiffFallback:
 * 1. Default render of diff fallback inspection card with header and scenario tabs.
 * 2. Evaluating diffs successfully with mocked codebaseDiffService response.
 * 3. Switching between MICRO, MODERATE, LARGE, and MASSIVE scenarios.
 * 4. Displaying truncation alerts when API files exceed hard limits.
 * 5. Testing graceful local fallback when service fails.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CodebaseDiffInspectionCard } from '../command-center/CodebaseDiffInspectionCard';

const { mockEvaluateDiff, mockParseNumstat } = vi.hoisted(() => ({
  mockEvaluateDiff: vi.fn(),
  mockParseNumstat: vi.fn(),
}));

vi.mock('@/services/memory/codebaseDiff', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    codebaseDiffService: {
      evaluateDiff: mockEvaluateDiff,
      parseNumstat: mockParseNumstat,
      checkHealth: vi.fn().mockResolvedValue({ status: 'ok', service: 'codebase_diff' }),
    },
  };
});

describe('CodebaseDiffInspectionCard (Item 144 P1)', () => {
  const sampleVerdict = {
    tier: 'moderate',
    total_files: 28,
    total_additions: 2350,
    total_deletions: 890,
    is_truncated: false,
    truncation_reason: null,
    active_files_count: 25,
    filtered_noise_files_count: 3,
    directory_aggregates: [
      {
        directory: 'src/services',
        file_count: 25,
        total_additions: 750,
        total_deletions: 240,
        primary_category: 'core_code',
      },
      {
        directory: 'root',
        file_count: 3,
        total_additions: 1600,
        total_deletions: 650,
        primary_category: 'lockfile',
      },
    ],
    summary_text: '[Diff Mode: MODERATE] Active source files retained, 3 noise files folded.',
    applied_optimizations: ['noise_filtration_active', 'patch_snippets_clipped'],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockEvaluateDiff.mockResolvedValue({
      verdict: sampleVerdict,
    });
  });

  it('renders the header and scenario switcher buttons', async () => {
    render(<CodebaseDiffInspectionCard />);

    expect(screen.getByText('代码库大 Diff 分级降级诊断')).toBeDefined();
    expect(screen.getByLabelText('切换到micro场景')).toBeDefined();
    expect(screen.getByLabelText('切换到moderate场景')).toBeDefined();
    expect(screen.getByLabelText('切换到large场景')).toBeDefined();
    expect(screen.getByLabelText('切换到massive场景')).toBeDefined();

    await waitFor(() => {
      expect(mockEvaluateDiff).toHaveBeenCalledTimes(1);
    });
  });

  it('displays evaluated verdict KPI cards and directory aggregates', async () => {
    render(<CodebaseDiffInspectionCard />);

    await waitFor(() => {
      expect(screen.getAllByText('MODERATE').length).toBeGreaterThan(0);
      expect(screen.getByText('执行层级 (Tier)')).toBeDefined();
      expect(screen.getByText('变更总量')).toBeDefined();
      expect(screen.getByText(/3 排除/)).toBeDefined();
      expect(screen.getByText('完整保真')).toBeDefined();
      expect(screen.getByText('src/services/')).toBeDefined();
      expect(screen.getByText('noise_filtration_active')).toBeDefined();
    });
  });

  it('switches to massive scenario and renders truncation warning', async () => {
    const massiveVerdict = {
      tier: 'massive',
      total_files: 3200,
      total_additions: 54000,
      total_deletions: 21000,
      is_truncated: true,
      truncation_reason: 'API file list truncated at 3000 cap',
      active_files_count: 0,
      filtered_noise_files_count: 0,
      directory_aggregates: [
        {
          directory: 'all',
          file_count: 3200,
          total_additions: 54000,
          total_deletions: 21000,
          primary_category: 'core_code',
        },
      ],
      summary_text: '[Diff Mode: MASSIVE] Truncation alert: over 3000 files.',
      applied_optimizations: ['api_truncation_protection', 'component_topology_summary'],
    };

    mockEvaluateDiff.mockResolvedValueOnce({ verdict: sampleVerdict });
    render(<CodebaseDiffInspectionCard />);

    await waitFor(() => {
      expect(mockEvaluateDiff).toHaveBeenCalledTimes(1);
    });

    mockEvaluateDiff.mockResolvedValueOnce({ verdict: massiveVerdict });
    const massiveButton = screen.getByLabelText('切换到massive场景');
    fireEvent.click(massiveButton);

    await waitFor(() => {
      expect(mockEvaluateDiff).toHaveBeenCalledTimes(2);
      expect(screen.getByText('已截断降级')).toBeDefined();
      expect(screen.getByText(/API file list truncated at 3000 cap/)).toBeDefined();
    });
  });

  it('falls back gracefully to offline client calculation on service failure', async () => {
    mockEvaluateDiff.mockRejectedValueOnce(new Error('Network error'));

    render(<CodebaseDiffInspectionCard />);

    await waitFor(() => {
      expect(screen.getByText(/Offline fallback verdict generated/i)).toBeDefined();
      expect(screen.getByText('client_offline_simulation')).toBeDefined();
    });
  });

  it('triggers manual refresh evaluation when refresh button is clicked', async () => {
    render(<CodebaseDiffInspectionCard />);

    await waitFor(() => {
      expect(mockEvaluateDiff).toHaveBeenCalledTimes(1);
    });

    const refreshBtn = screen.getByLabelText('刷新 Diff 评估诊断');
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(mockEvaluateDiff).toHaveBeenCalledTimes(2);
    });
  });
});
