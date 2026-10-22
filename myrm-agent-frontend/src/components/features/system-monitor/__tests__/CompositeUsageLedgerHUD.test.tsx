import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CompositeUsageLedgerHUD } from '../CompositeUsageLedgerHUD';
import type {
  CompositeUsageRecordItem,
  LedgerSummaryData,
} from '../compositeUsageLedgerTypes';

describe('CompositeUsageLedgerHUD', () => {
  const mockSummary: LedgerSummaryData = {
    total_records: 3,
    total_calls: 15,
    total_input_tokens: 45000,
    total_output_tokens: 12000,
    total_cache_tokens: 28000,
    total_estimated_usd: 0.155,
    total_actual_usd: 0.162,
    reconciled_records_count: 2,
    discrepancy_records_count: 1,
    task_spend_distribution: {
      main_turn: 0.105,
      artifact_compile: 0.045,
      background_review: 0.012,
    },
    model_spend_distribution: {
      'claude-3-7-sonnet': 0.12,
      'gpt-4o': 0.042,
    },
  };

  const mockRecords: CompositeUsageRecordItem[] = [
    {
      session_id: 'sess_1001',
      model: 'claude-3-7-sonnet',
      billing_provider: 'anthropic',
      billing_base_url: 'https://api.anthropic.com/v1',
      billing_mode: 'standard',
      task: 'main_turn',
      api_call_count: 8,
      input_tokens: 25000,
      output_tokens: 6000,
      cache_read_tokens: 18000,
      cache_write_tokens: 0,
      reasoning_tokens: 1200,
      estimated_cost_usd: 0.105,
      actual_cost_usd: 0.108,
      cost_status: 'RECONCILED',
      discrepancy_pct: 2.8,
      first_seen_ms: 1710000000000,
      last_seen_ms: 1710000005000,
    },
    {
      session_id: 'sess_1001',
      model: 'claude-3-7-sonnet',
      billing_provider: 'anthropic',
      billing_base_url: 'https://api.anthropic.com/v1',
      billing_mode: 'standard',
      task: 'artifact_compile',
      api_call_count: 5,
      input_tokens: 15000,
      output_tokens: 5000,
      cache_read_tokens: 10000,
      cache_write_tokens: 0,
      reasoning_tokens: 0,
      estimated_cost_usd: 0.045,
      actual_cost_usd: 0.054,
      cost_status: 'DISCREPANCY_ALERT',
      discrepancy_pct: 20.0,
      first_seen_ms: 1710000006000,
      last_seen_ms: 1710000010000,
    },
  ];

  it('renders header, 4 KPI cards, task spend breakdown, and ledger rows', () => {
    const onRefresh = vi.fn();
    const onReset = vi.fn();
    const onReconcile = vi.fn();

    render(
      <CompositeUsageLedgerHUD
        summary={mockSummary}
        records={mockRecords}
        onRefresh={onRefresh}
        onReset={onReset}
        onReconcile={onReconcile}
      />
    );

    // 头部信息
    expect(screen.getByText('六维复合主键用量分摊账本与双轨对账 HUD')).toBeInTheDocument();
    expect(screen.getByText('Hermes 风格持久账本')).toBeInTheDocument();

    // 核心 KPI
    expect(screen.getByText('$0.1550')).toBeInTheDocument();
    expect(screen.getByText('$0.1620')).toBeInTheDocument();
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    expect(screen.getByText(/1 笔超差/)).toBeInTheDocument();
    expect(screen.getByText('15 次')).toBeInTheDocument();

    // 任务细粒度归因
    expect(screen.getAllByText('main_turn')[0]).toBeInTheDocument();
    expect(screen.getAllByText('artifact_compile')[0]).toBeInTheDocument();
    expect(screen.getByText('background_review')).toBeInTheDocument();

    // 模型开销分布
    expect(screen.getAllByText('claude-3-7-sonnet')[0]).toBeInTheDocument();
    expect(screen.getByText('gpt-4o')).toBeInTheDocument();

    // 表格记录与徽标
    expect(screen.getAllByText('sess_1001')[0]).toBeInTheDocument();
    expect(screen.getByText('已对账 (偏差 2.8%)')).toBeInTheDocument();
    expect(screen.getByText('⚠️ 偏差告警 (偏差 20.0%)')).toBeInTheDocument();
  });

  it('handles task filtering and trigger callbacks correctly', async () => {
    const onRefresh = vi.fn();
    const onReset = vi.fn();
    const onReconcile = vi.fn().mockResolvedValue(undefined);

    render(
      <CompositeUsageLedgerHUD
        summary={mockSummary}
        records={mockRecords}
        onRefresh={onRefresh}
        onReset={onReset}
        onReconcile={onReconcile}
      />
    );

    // 触发刷新
    const refreshBtn = screen.getByRole('button', { name: '刷新账本' });
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);

    // 触发清空
    const resetBtn = screen.getByRole('button', { name: '清空账本' });
    fireEvent.click(resetBtn);
    expect(onReset).toHaveBeenCalledTimes(1);

    // 触发核销对账
    const reconcileBtns = screen.getAllByRole('button', { name: '核销对账' });
    await React.act(async () => {
      fireEvent.click(reconcileBtns[0]);
    });
    expect(onReconcile).toHaveBeenCalledWith(mockRecords[0], mockRecords[0].estimated_cost_usd);

    // 切换任务过滤
    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'artifact_compile' } });
    expect(screen.queryByText('已对账 (偏差 2.8%)')).not.toBeInTheDocument();
    expect(screen.getByText('⚠️ 偏差告警 (偏差 20.0%)')).toBeInTheDocument();
  });

  it('renders empty states gracefully', () => {
    const emptySummary: LedgerSummaryData = {
      total_records: 0,
      total_calls: 0,
      total_input_tokens: 0,
      total_output_tokens: 0,
      total_cache_tokens: 0,
      total_estimated_usd: 0.0,
      total_actual_usd: 0.0,
      reconciled_records_count: 0,
      discrepancy_records_count: 0,
      task_spend_distribution: {},
      model_spend_distribution: {},
    };

    render(<CompositeUsageLedgerHUD summary={emptySummary} records={[]} />);

    expect(screen.getByText('暂无任务分摊记录')).toBeInTheDocument();
    expect(screen.getByText('暂无模型分摊记录')).toBeInTheDocument();
    expect(screen.getByText('暂无复合账本记录')).toBeInTheDocument();
  });
});
