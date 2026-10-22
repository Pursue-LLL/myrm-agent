import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  ToolCompositionCard,
  computeToolComposition,
} from '../ToolCompositionCard';
import type { ToolStabilityDaily } from '@/services/statistics';

describe('ToolCompositionCard & computeToolComposition', () => {
  const mockDailyRecords: ToolStabilityDaily[] = [
    {
      date: '2026-10-10',
      tool_name: 'bash_command',
      total_calls: 50,
      success_count: 48,
      failure_count: 2,
      timeout_count: 0,
      avg_duration_ms: 200,
      p90_duration_ms: 300,
      p99_duration_ms: 500,
      failure_rate: 0.04,
      failure_reasons: {},
    },
    {
      date: '2026-10-11',
      tool_name: 'bash_command',
      total_calls: 50,
      success_count: 49,
      failure_count: 1,
      timeout_count: 0,
      avg_duration_ms: 200,
      p90_duration_ms: 250,
      p99_duration_ms: 400,
      failure_rate: 0.02,
      failure_reasons: {},
    },
    {
      date: '2026-10-10',
      tool_name: 'file_search',
      total_calls: 60,
      success_count: 60,
      failure_count: 0,
      timeout_count: 0,
      avg_duration_ms: 100,
      p90_duration_ms: 150,
      p99_duration_ms: 200,
      failure_rate: 0,
      failure_reasons: {},
    },
    {
      date: '2026-10-10',
      tool_name: 'web_crawler',
      total_calls: 30,
      success_count: 28,
      failure_count: 2,
      timeout_count: 0,
      avg_duration_ms: 800,
      p90_duration_ms: 1000,
      p99_duration_ms: 1500,
      failure_rate: 0.06,
      failure_reasons: {},
    },
    {
      date: '2026-10-10',
      tool_name: 'git_status',
      total_calls: 10,
      success_count: 10,
      failure_count: 0,
      timeout_count: 0,
      avg_duration_ms: 50,
      p90_duration_ms: 60,
      p99_duration_ms: 80,
      failure_rate: 0,
      failure_reasons: {},
    },
  ];

  it('computes tool composition accurately with top 3 and collapsible others', () => {
    const summary = computeToolComposition(mockDailyRecords);

    // Total calls: bash (100) + file_search (60) + web_crawler (30) + git_status (10) = 200
    expect(summary.totalCalls).toBe(200);

    // Top 3 ranking check
    expect(summary.topTools.length).toBe(3);
    expect(summary.topTools[0].tool_name).toBe('bash_command');
    expect(summary.topTools[0].calls).toBe(100);
    expect(summary.topTools[0].calls_percent).toBe(50.0);

    expect(summary.topTools[1].tool_name).toBe('file_search');
    expect(summary.topTools[1].calls).toBe(60);
    expect(summary.topTools[1].calls_percent).toBe(30.0);

    expect(summary.topTools[2].tool_name).toBe('web_crawler');
    expect(summary.topTools[2].calls).toBe(30);
    expect(summary.topTools[2].calls_percent).toBe(15.0);

    // Other tools check (git_status)
    expect(summary.otherTools.length).toBe(1);
    expect(summary.otherTools[0].tool_name).toBe('git_status');
    expect(summary.otherCallsTotal).toBe(10);
    expect(summary.otherCallsPercent).toBe(5.0);

    // Sum of percentages equals 100%
    const totalPercentage =
      summary.topTools.reduce((acc, cur) => acc + cur.calls_percent, 0) +
      summary.otherCallsPercent;
    expect(Math.round(totalPercentage)).toBe(100);
  });

  it('handles empty records gracefully without errors', () => {
    const emptySummary = computeToolComposition([]);
    expect(emptySummary.totalCalls).toBe(0);
    expect(emptySummary.topTools.length).toBe(0);
    expect(emptySummary.otherTools.length).toBe(0);
  });

  it('renders ToolCompositionCard with UI items and toggleable container', () => {
    const onDaysChange = vi.fn();
    render(
      <ToolCompositionCard
        dailyRecords={mockDailyRecords}
        days={30}
        onDaysChange={onDaysChange}
      />
    );

    expect(screen.getByTestId('tool-composition-card')).toBeDefined();
    expect(screen.getByText(/周期工具构成分析/)).toBeDefined();
    expect(screen.getByText('bash_command')).toBeDefined();
    expect(screen.getByText('file_search')).toBeDefined();
    expect(screen.getByText('web_crawler')).toBeDefined();

    // Verify other tools toggle button
    const toggleBtn = screen.getByTestId('toggle-other-tools');
    expect(toggleBtn).toBeDefined();
    expect(screen.queryByTestId('other-tools-container')).toBeNull();

    // Click toggle button to expand
    fireEvent.click(toggleBtn);
    expect(screen.getByTestId('other-tools-container')).toBeDefined();
    expect(screen.getByText('git_status')).toBeDefined();

    // Verify 7 days button click
    const sevenDaysBtn = screen.getByRole('button', { name: '7 天' });
    fireEvent.click(sevenDaysBtn);
    expect(onDaysChange).toHaveBeenCalledWith(7);
  });
});
