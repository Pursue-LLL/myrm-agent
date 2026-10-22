/**
 * [INPUT]: MemoryBackendMetricsDashboard component, mock MemoryBackendMetricsReportItem.
 * [OUTPUT]: Vitest test suite verifying latency percentiles, backend/phase filtering, opt-in toggles, and resets.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/__tests__/MemoryBackendMetricsDashboard.test.tsx
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryBackendMetricsDashboard } from '../MemoryBackendMetricsDashboard';
import { MemoryBackendMetricsReportItem } from '../memoryBackendMetricsTypes';

describe('MemoryBackendMetricsDashboard Component', () => {
  const mockReport: MemoryBackendMetricsReportItem = {
    opt_in_enabled: true,
    total_samples: 30,
    timestamp_ms: 1791800000000,
    backend_stats: [
      {
        backend: 'sqlite_fts5',
        operation: 'recall',
        phase: 'collect',
        total_operations: 20,
        success_count: 20,
        success_rate: 1.0,
        degraded_count: 0,
        avg_duration_ms: 14.5,
        p50_duration_ms: 12.0,
        p95_duration_ms: 22.5,
      },
      {
        backend: 'qdrant',
        operation: 'recall',
        phase: 'rerank',
        total_operations: 10,
        success_count: 9,
        success_rate: 0.9,
        degraded_count: 1,
        avg_duration_ms: 88.0,
        p50_duration_ms: 75.0,
        p95_duration_ms: 145.0,
      },
    ],
  };

  it('renders summary statistics and metric rows accurately', () => {
    render(<MemoryBackendMetricsDashboard report={mockReport} />);

    // Header
    expect(screen.getByText(/Memory Backend Telemetry & Phase Breakdown/i)).toBeInTheDocument();

    // Top metrics
    expect(screen.getByTestId('total-samples-val')).toHaveTextContent('30');
    expect(screen.getByTestId('active-backends-val')).toHaveTextContent('2');
    expect(screen.getByTestId('degraded-count-val')).toHaveTextContent('1');

    // Rows
    expect(screen.getByTestId('stat-row-sqlite_fts5-collect')).toBeInTheDocument();
    expect(screen.getByTestId('stat-row-qdrant-rerank')).toBeInTheDocument();

    // P50 / P95 Latencies
    expect(screen.getByText('12.0')).toBeInTheDocument();
    expect(screen.getByText('22.5')).toBeInTheDocument();
    expect(screen.getByText('75.0')).toBeInTheDocument();
    expect(screen.getByText('145.0')).toBeInTheDocument();
  });

  it('handles opt-in toggle and reset callbacks correctly', () => {
    const handleToggleOptIn = vi.fn();
    const handleReset = vi.fn();

    render(
      <MemoryBackendMetricsDashboard
        report={mockReport}
        onToggleOptIn={handleToggleOptIn}
        onReset={handleReset}
      />
    );

    const toggleBtn = screen.getByTestId('toggle-opt-in-btn');
    expect(toggleBtn).toHaveTextContent('Opt-in Label: Enabled');
    fireEvent.click(toggleBtn);
    expect(handleToggleOptIn).toHaveBeenCalledWith(false);

    const resetBtn = screen.getByTestId('reset-metrics-btn');
    fireEvent.click(resetBtn);
    expect(handleReset).toHaveBeenCalledTimes(1);
  });

  it('filters rows by backend and phase correctly', () => {
    render(<MemoryBackendMetricsDashboard report={mockReport} />);

    // Filter by QDRANT backend
    const qdrantBtn = screen.getByText('QDRANT');
    fireEvent.click(qdrantBtn);

    expect(screen.queryByTestId('stat-row-sqlite_fts5-collect')).not.toBeInTheDocument();
    expect(screen.getByTestId('stat-row-qdrant-rerank')).toBeInTheDocument();

    // Filter by COLLECT phase while Qdrant is selected -> empty state
    const collectBtn = screen.getByText('COLLECT');
    fireEvent.click(collectBtn);

    expect(screen.queryByTestId('stat-row-qdrant-rerank')).not.toBeInTheDocument();
    expect(
      screen.getByText(/No memory operation telemetry recorded for this filter/i)
    ).toBeInTheDocument();
  });
});
