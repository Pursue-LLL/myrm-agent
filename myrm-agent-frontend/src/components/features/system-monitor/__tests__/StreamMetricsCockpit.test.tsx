import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StreamMetricsCockpit } from '../StreamMetricsCockpit';
import type {
  StreamCallSession,
  StreamMetricsAggregate,
} from '../streamMetricsTypes';

describe('StreamMetricsCockpit', () => {
  const mockAggregate: StreamMetricsAggregate = {
    total_calls: 10,
    success_calls: 8,
    error_calls: 1,
    cancelled_calls: 1,
    timeout_calls: 0,
    total_chunks: 2500,
    total_tokens: 12000,
    avg_ttft_ms: 125.4,
    avg_duration_ms: 3200.0,
    success_rate_pct: 80.0,
    chunk_inflation_ratio: 250.0,
  };

  const mockSessions: StreamCallSession[] = [
    {
      call_id: 'call_live_001',
      model_name: 'claude-3-7-sonnet-20250219',
      provider: 'anthropic',
      start_time_ms: 1710000000000,
      ttft_ms: 110.0,
      end_time_ms: 1710000003000,
      total_duration_ms: 3000.0,
      chunk_count: 280,
      total_tokens: 1400,
      outcome: 'SUCCESS',
      error_message: null,
      is_finalized: true,
    },
    {
      call_id: 'call_live_002',
      model_name: 'gpt-4o',
      provider: 'openai',
      start_time_ms: 1710000010000,
      ttft_ms: 180.0,
      end_time_ms: 1710000012000,
      total_duration_ms: 2000.0,
      chunk_count: 50,
      total_tokens: 250,
      outcome: 'CANCELLED',
      error_message: null,
      is_finalized: true,
    },
  ];

  it('renders aggregate KPI cards, inflation ratio, and TTFT metrics accurately', () => {
    const onRefresh = vi.fn();
    render(
      <StreamMetricsCockpit
        aggregate={mockAggregate}
        recentSessions={mockSessions}
        onRefresh={onRefresh}
      />
    );

    // 标题与防污染徽章
    expect(screen.getByText('流式调用按最终结果计量驾驶舱')).toBeInTheDocument();
    expect(screen.getByText('防中间 Chunk 污染已生效')).toBeInTheDocument();

    // KPI 数据卡片
    expect(screen.getAllByText('10').length).toBeGreaterThanOrEqual(1); // total_calls
    expect(screen.getByText('80.0%')).toBeInTheDocument(); // success_rate_pct
    expect(screen.getByText('250.0×')).toBeInTheDocument(); // chunk_inflation_ratio
    expect(screen.getByText('125 ms')).toBeInTheDocument(); // avg_ttft_ms

    // 四色终态分布
    expect(screen.getByText('成功完成 (SUCCESS)')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument(); // success_calls
    expect(screen.getByText('异常失败 (ERROR)')).toBeInTheDocument();
    expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(2); // error_calls & cancelled_calls

    // 防污染保证描述
    expect(screen.getByText('可观测性数据地基真实性保证 (Data Integrity Guarantee)')).toBeInTheDocument();
    expect(screen.getByText(/2,500/)).toBeInTheDocument(); // total_chunks formatted

    // 刷新按钮
    const refreshBtn = screen.getByText('刷新指标');
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('renders recent call sessions table with outcomes and chunk counts', () => {
    render(
      <StreamMetricsCockpit
        aggregate={mockAggregate}
        recentSessions={mockSessions}
      />
    );

    // 表格内容
    expect(screen.getByText('call_live_001')).toBeInTheDocument();
    expect(screen.getByText('claude-3-7-sonnet-20250219')).toBeInTheDocument();
    expect(screen.getByText('280 个')).toBeInTheDocument();
    expect(screen.getByText('成功完成')).toBeInTheDocument();

    expect(screen.getByText('call_live_002')).toBeInTheDocument();
    expect(screen.getByText('gpt-4o')).toBeInTheDocument();
    expect(screen.getByText('50 个')).toBeInTheDocument();
    expect(screen.getByText('主动取消')).toBeInTheDocument();
  });
});
