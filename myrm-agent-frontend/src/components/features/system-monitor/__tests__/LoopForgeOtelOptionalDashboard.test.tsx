import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LoopForgeOtelOptionalDashboard } from '../LoopForgeOtelOptionalDashboard';
import type { LocalSinkStatusData, LocalSpanItem } from '../localSinkTypes';

describe('LoopForgeOtelOptionalDashboard', () => {
  const mockStatus: LocalSinkStatusData = {
    is_enabled: true,
    sink_path: '/Users/test/.myrm/telemetry/spans.jsonl',
    buffered_spans_count: 42,
    persisted_spans_count: 156,
    file_size_bytes: 1024 * 54, // 54 KB
    last_flush_iso: '2026-10-12T15:30:00Z',
  };

  const mockSpans: LocalSpanItem[] = [
    {
      trace_id: 'tr_test_101',
      span_id: 'sp_test_201',
      name: 'tool_execution:bash',
      start_time_iso: '2026-10-12T15:29:00Z',
      end_time_iso: '2026-10-12T15:29:01Z',
      duration_ms: 124.5,
      status: 'OK',
      attributes: { cmd: 'pytest -v', exit_code: '0' },
    },
    {
      trace_id: 'tr_test_101',
      span_id: 'sp_test_202',
      name: 'llm_inference:claude-3-7-sonnet',
      start_time_iso: '2026-10-12T15:29:02Z',
      end_time_iso: '2026-10-12T15:29:03Z',
      duration_ms: 850.0,
      status: 'OK',
      attributes: { model: 'claude-3-7-sonnet' },
    },
  ];

  it('renders dashboard with active badge, metric cards, storage path, and span list', () => {
    const onToggleEnabled = vi.fn();
    const onRefresh = vi.fn();
    const onSimulateSpan = vi.fn();

    render(
      <LoopForgeOtelOptionalDashboard
        status={mockStatus}
        spans={mockSpans}
        onToggleEnabled={onToggleEnabled}
        onRefresh={onRefresh}
        onSimulateSpan={onSimulateSpan}
      />
    );

    // 标题与活跃徽章
    expect(
      screen.getByText('OpenTelemetry 缺失降级与本地盘兜底大盘 (LoopForge OTel Dashboard)')
    ).toBeInTheDocument();
    expect(
      screen.getByText('本地盘落盘兜底中 (Local Disk Active)')
    ).toBeInTheDocument();

    // 核心卡片
    expect(screen.getByText('156')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('54.0 KB')).toBeInTheDocument();
    expect(screen.getByText('/Users/test/.myrm/telemetry/spans.jsonl')).toBeInTheDocument();

    // 链路列表
    expect(screen.getByText('tool_execution:bash')).toBeInTheDocument();
    expect(screen.getByText('124.5 ms')).toBeInTheDocument();
    expect(screen.getByText('llm_inference:claude-3-7-sonnet')).toBeInTheDocument();
    expect(screen.getByText('850 ms')).toBeInTheDocument();

    // 交互按钮
    const refreshBtn = screen.getByText('刷新状态');
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);

    const simBtn = screen.getByText('模拟上报 Span');
    fireEvent.click(simBtn);
    expect(onSimulateSpan).toHaveBeenCalledTimes(1);

    const toggleBtn = screen.getByText('关闭本地落盘');
    fireEvent.click(toggleBtn);
    expect(onToggleEnabled).toHaveBeenCalledWith(false);
  });
});
