/**
 * [INPUT]: ActiveSkillSpanTelemetryCockpit component, mock ActiveSkillTelemetryReportItem and SkillSpanRecordItem array.
 * [OUTPUT]: Vitest test suite verifying skill aggregation rows, P95 latencies, error counts, filtering, and callbacks.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/__tests__/ActiveSkillSpanTelemetryCockpit.test.tsx
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ActiveSkillSpanTelemetryCockpit } from '../ActiveSkillSpanTelemetryCockpit';
import {
  ActiveSkillTelemetryReportItem,
  SkillSpanRecordItem,
} from '../activeSkillTelemetryTypes';

describe('ActiveSkillSpanTelemetryCockpit Component', () => {
  const mockReport: ActiveSkillTelemetryReportItem = {
    total_spans_recorded: 15,
    skills_count: 2,
    unattributed_spans_count: 3,
    timestamp_ms: 1791800000000,
    skill_aggregations: [
      {
        skill_name: 'git_master',
        total_spans: 10,
        error_spans: 0,
        error_rate: 0.0,
        avg_duration_ms: 45.0,
        p95_duration_ms: 95.0,
      },
      {
        skill_name: 'code_reviewer',
        total_spans: 2,
        error_spans: 1,
        error_rate: 0.5,
        avg_duration_ms: 110.0,
        p95_duration_ms: 150.0,
      },
    ],
  };

  const mockSpans: SkillSpanRecordItem[] = [
    {
      span_id: 'span-001',
      trace_id: 'trace-001',
      name: 'tool.git_status',
      active_skill: 'git_master',
      duration_ms: 30.0,
      status: 'ok',
      attributes: { 'myrm.skill.active': 'git_master' },
      timestamp_ms: 1791800001000,
    },
    {
      span_id: 'span-002',
      trace_id: 'trace-002',
      name: 'llm.review_diff',
      active_skill: 'code_reviewer',
      duration_ms: 135.0,
      status: 'error',
      attributes: { 'myrm.skill.active': 'code_reviewer' },
      timestamp_ms: 1791800002000,
    },
    {
      span_id: 'span-003',
      trace_id: 'trace-003',
      name: 'system.ping',
      active_skill: null,
      duration_ms: 5.0,
      status: 'ok',
      attributes: {},
      timestamp_ms: 1791800003000,
    },
  ];

  it('renders summary statistics and skill aggregation rows accurately', () => {
    render(<ActiveSkillSpanTelemetryCockpit report={mockReport} spans={mockSpans} />);

    // Header title
    expect(
      screen.getByText(/Active Skill Span Telemetry & Attribution Cockpit/i)
    ).toBeInTheDocument();

    // Top cards
    expect(screen.getByTestId('total-spans-val')).toHaveTextContent('15');
    expect(screen.getByTestId('active-skills-val')).toHaveTextContent('2');
    expect(screen.getByTestId('unattributed-spans-val')).toHaveTextContent('3');
    expect(screen.getByTestId('total-errors-val')).toHaveTextContent('1');

    // Skill Aggregation Rows
    expect(screen.getByTestId('skill-agg-row-git_master')).toBeInTheDocument();
    expect(screen.getByTestId('skill-agg-row-code_reviewer')).toBeInTheDocument();

    // P95 duration checks
    expect(screen.getByText('95.0')).toBeInTheDocument();
    expect(screen.getAllByText('150.0').length).toBeGreaterThanOrEqual(1);
  });

  it('handles refresh and reset button callbacks', () => {
    const handleRefresh = vi.fn();
    const handleReset = vi.fn();

    render(
      <ActiveSkillSpanTelemetryCockpit
        report={mockReport}
        spans={mockSpans}
        onRefresh={handleRefresh}
        onReset={handleReset}
      />
    );

    const refreshBtn = screen.getByTestId('refresh-telemetry-btn');
    fireEvent.click(refreshBtn);
    expect(handleRefresh).toHaveBeenCalledTimes(1);

    const resetBtn = screen.getByTestId('reset-telemetry-btn');
    fireEvent.click(resetBtn);
    expect(handleReset).toHaveBeenCalledTimes(1);
  });

  it('filters span stream by active skill correctly', () => {
    render(<ActiveSkillSpanTelemetryCockpit report={mockReport} spans={mockSpans} />);

    // Initially all spans exist
    expect(screen.getByTestId('span-row-span-001')).toBeInTheDocument();
    expect(screen.getByTestId('span-row-span-002')).toBeInTheDocument();
    expect(screen.getByTestId('span-row-span-003')).toBeInTheDocument();

    // Filter by git_master
    const filterGitBtn = screen.getByTestId('filter-skill-git_master');
    fireEvent.click(filterGitBtn);

    expect(screen.getByTestId('span-row-span-001')).toBeInTheDocument();
    expect(screen.queryByTestId('span-row-span-002')).not.toBeInTheDocument();
    expect(screen.queryByTestId('span-row-span-003')).not.toBeInTheDocument();

    // Filter by unattributed
    const filterUnattrBtn = screen.getByTestId('filter-skill-unattributed');
    fireEvent.click(filterUnattrBtn);

    expect(screen.queryByTestId('span-row-span-001')).not.toBeInTheDocument();
    expect(screen.getByTestId('span-row-span-003')).toBeInTheDocument();
  });
});
