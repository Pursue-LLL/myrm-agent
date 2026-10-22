import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AmbientAuxiliaryAccountingHUD } from '../AmbientAuxiliaryAccountingHUD';
import {
  AmbientAccountingReportData,
  AuxiliaryUsageSnapshotItem,
} from '../ambientAuxiliaryAccountingTypes';

describe('AmbientAuxiliaryAccountingHUD Component', () => {
  const mockReport: AmbientAccountingReportData = {
    total_invocations: 12,
    total_cost_usd: 0.125,
    core_dialogue_cost_usd: 0.080,
    auxiliary_cost_usd: 0.045,
    auxiliary_cost_share_pct: 36.0,
    task_summaries: [
      {
        task_name: 'main_dialogue',
        call_count: 5,
        total_input_tokens: 15000,
        total_output_tokens: 2500,
        total_tokens: 17500,
        total_cost_usd: 0.080,
        avg_duration_ms: 1200.0,
        share_pct: 64.0,
      },
      {
        task_name: 'context_compression',
        call_count: 4,
        total_input_tokens: 8000,
        total_output_tokens: 800,
        total_tokens: 8800,
        total_cost_usd: 0.030,
        avg_duration_ms: 450.0,
        share_pct: 24.0,
      },
      {
        task_name: 'vision_prep',
        call_count: 3,
        total_input_tokens: 4000,
        total_output_tokens: 300,
        total_tokens: 4300,
        total_cost_usd: 0.015,
        avg_duration_ms: 320.0,
        share_pct: 12.0,
      },
    ],
    prompt_cache_purity_preserved: true,
    generated_at_ms: 1718000000000,
  };

  const mockSnapshots: AuxiliaryUsageSnapshotItem[] = [
    {
      session_id: 'sess_hud_01',
      task_type: 'main_dialogue',
      custom_task_name: '',
      effective_task_name: 'main_dialogue',
      model: 'gpt-4o',
      input_tokens: 3000,
      output_tokens: 500,
      total_tokens: 3500,
      duration_ms: 950.0,
      cost_usd: 0.018,
      timestamp_ms: 1718000001000,
    },
    {
      session_id: 'sess_hud_01',
      task_type: 'context_compression',
      custom_task_name: '',
      effective_task_name: 'context_compression',
      model: 'gpt-4o-mini',
      input_tokens: 2000,
      output_tokens: 200,
      total_tokens: 2200,
      duration_ms: 380.0,
      cost_usd: 0.007,
      timestamp_ms: 1718000002000,
    },
  ];

  it('renders overview metrics cards and cache purity badge correctly', () => {
    render(<AmbientAuxiliaryAccountingHUD report={mockReport} snapshots={mockSnapshots} />);

    expect(screen.getByText('环境感知式用量记账与任务归因 HUD')).toBeInTheDocument();
    expect(screen.getByText('✓ Prompt Cache 纯度隔离已保护')).toBeInTheDocument();
    expect(screen.getByText('$0.1250')).toBeInTheDocument();
    expect(screen.getByText('$0.0800')).toBeInTheDocument();
    expect(screen.getByText('$0.0450')).toBeInTheDocument();
    expect(screen.getByText('36.0%')).toBeInTheDocument();
  });

  it('renders task dimension attribution summaries table', () => {
    render(<AmbientAuxiliaryAccountingHUD report={mockReport} snapshots={mockSnapshots} />);

    expect(screen.getByText('任务维度归因与支出占比 (Task Dimension Breakdown)')).toBeInTheDocument();
    // Use getAllByText for items that might be rendered in both table and dropdown
    const mainItems = screen.getAllByText('main_dialogue');
    expect(mainItems.length).toBeGreaterThanOrEqual(1);

    const compItems = screen.getAllByText('context_compression');
    const share64 = screen.getAllByText('64.0%');
    expect(share64.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('24.0%')).toBeInTheDocument();
  });

  it('handles refresh and reset callback interactions', async () => {
    const handleRefresh = vi.fn();
    const handleReset = vi.fn();

    render(
      <AmbientAuxiliaryAccountingHUD
        report={mockReport}
        snapshots={mockSnapshots}
        onRefresh={handleRefresh}
        onReset={handleReset}
      />
    );

    const refreshBtn = screen.getByRole('button', { name: '刷新大盘' });
    await React.act(async () => {
      fireEvent.click(refreshBtn);
    });
    expect(handleRefresh).toHaveBeenCalledTimes(1);

    const resetBtn = screen.getByRole('button', { name: '清空用量' });
    await React.act(async () => {
      fireEvent.click(resetBtn);
    });
    expect(handleReset).toHaveBeenCalledTimes(1);
  });
});
