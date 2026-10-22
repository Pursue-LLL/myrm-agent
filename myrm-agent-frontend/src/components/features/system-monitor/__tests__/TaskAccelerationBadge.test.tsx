import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { TaskAccelerationBadge } from '../TaskAccelerationBadge';
import { ProductivityRoiDashboard } from '../ProductivityRoiDashboard';
import type { LaborAccelerationSummary, MonthlyProductivitySummary } from '../types';

describe('TaskAccelerationBadge & ProductivityRoiDashboard', () => {
  const mockSummary: LaborAccelerationSummary = {
    task_id: 'task-hermes-labor-999',
    task_elapsed_seconds: 45.0,
    total_hours_saved: 1.23,
    acceleration_factor: 98.4,
    hourly_rate_usd: 35.0,
    estimated_saved_value_usd: 43.05,
    compute_cost_usd: 0.05,
    roi_ratio: 861.0,
    breakdown: [
      {
        action_type: 'web_research',
        label: '多信源深度搜索与交叉比对',
        count: 4,
        hours_per_unit: 0.1,
        total_hours_saved: 0.4,
      },
      {
        action_type: 'code_execution',
        label: '代码生成沙箱运行与自动排障',
        count: 1,
        hours_per_unit: 0.3333,
        total_hours_saved: 0.3333,
      },
    ],
    created_at: 1700000000,
  };

  const mockMonthly: MonthlyProductivitySummary = {
    month: '2026-10',
    total_tasks_automated: 142,
    total_hours_saved: 68.5,
    total_saved_value_usd: 2397.5,
    total_compute_cost_usd: 19.18,
    overall_roi_ratio: 125.0,
    top_saving_categories: [
      {
        action_type: 'code_execution',
        label: '代码生成沙箱运行与自动排障',
        count: 75,
        hours_per_unit: 0.3333,
        total_hours_saved: 25.0,
      },
      {
        action_type: 'web_research',
        label: '多信源深度搜索与交叉比对',
        count: 180,
        hours_per_unit: 0.1,
        total_hours_saved: 18.0,
      },
    ],
  };

  beforeEach(() => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it('renders TaskAccelerationBadge with stats and handles copy & toggle', async () => {
    render(<TaskAccelerationBadge summary={mockSummary} />);

    // 核心徽章指标
    expect(screen.getByText('加速 98.4×')).toBeInTheDocument();
    expect(screen.getByText('挽回 ~1.23h')).toBeInTheDocument();
    expect(screen.getByText('用时 45s')).toBeInTheDocument();

    // 点击复制
    const copyBtn = screen.getByRole('button', { name: /复制生产力战报/i });
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        expect.stringContaining('AI 效能加速: 98.4×')
      );
    });

    // 展开明细
    const toggleBtn = screen.getByRole('button', { name: /展开工时置换明细/i });
    fireEvent.click(toggleBtn);

    expect(screen.getByText('人工劳务置换等效矩阵')).toBeInTheDocument();
    expect(screen.getByText(/多信源深度搜索与交叉比对/i)).toBeInTheDocument();
    expect(screen.getByText('+$43.05')).toBeInTheDocument();
  });

  it('renders ProductivityRoiDashboard with overview and top savings', () => {
    render(<ProductivityRoiDashboard summary={mockMonthly} />);

    // 标题与月份
    expect(screen.getByText(/白领劳务效能与生产力 ROI 看板/i)).toBeInTheDocument();
    expect(screen.getByText('2026-10')).toBeInTheDocument();
    expect(screen.getByText(/累计接管 142 项高频复杂劳务/i)).toBeInTheDocument();

    // 综合 ROI
    expect(screen.getByText(/125.0× 收益倍率/i)).toBeInTheDocument();

    // 核心四宫格
    expect(screen.getByText('68.5')).toBeInTheDocument();
    expect(screen.getByText('$2397.50')).toBeInTheDocument();
    expect(screen.getByText('$19.18')).toBeInTheDocument();
    expect(screen.getByText('$0.28')).toBeInTheDocument(); // 19.18 / 68.5 ≈ 0.28

    // 排行榜
    expect(screen.getByText(/高频劳务节省工时分类排行/i)).toBeInTheDocument();
    expect(screen.getAllByText(/代码生成沙箱运行与自动排障/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/多信源深度搜索与交叉比对/i).length).toBeGreaterThanOrEqual(1);
  });
});
