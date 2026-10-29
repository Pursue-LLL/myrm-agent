import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ProductivityRoiDashboard } from '../ProductivityRoiDashboard';
import type { MonthlyProductivitySummary } from '../types';

describe('ProductivityRoiDashboard', () => {
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
