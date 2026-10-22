import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CacheSavingsRoiHUD } from '../CacheSavingsRoiHUD';
import type {
  BudgetGuardEvaluation,
  CacheSavingsMetrics,
  CostDriftAlert,
} from '../tokenEconomicsTypes';

describe('CacheSavingsRoiHUD', () => {
  const mockMetrics: CacheSavingsMetrics = {
    task_id: 'task-opt-01',
    model_name: 'deepseek-chat',
    cache_hit_rate_pct: 99.1,
    baseline_cost_rmb: 10.45,
    actual_cost_rmb: 1.55,
    saved_amount_rmb: 8.90,
    saved_percentage: 85.17,
    burn_rate_rmb_per_minute: 0.42,
  };

  const mockDriftAlert: CostDriftAlert = {
    task_category: 'code_refactoring',
    model_name: 'deepseek-chat',
    current_unit_cost_per_k: 0.025,
    baseline_unit_cost_per_k: 0.010,
    drift_percentage: 150.0,
    is_significant_drift: true,
    reason: 'CACHE_HIT_DEGRADED',
    explanation: 'Prompt 缓存击穿劣化，导致单位成本显著增加 150.0%。',
  };

  it('renders 99% cache savings badge and comparative cost metrics', () => {
    render(<CacheSavingsRoiHUD metrics={mockMetrics} />);

    expect(screen.getByText('99% 缓存节流真实收益')).toBeInTheDocument();
    expect(screen.getByTestId('cache-hit-badge')).toHaveTextContent('命中率 99.1%');
    expect(screen.getByTestId('savings-headline')).toHaveTextContent('已为您净节省 ¥8.90');
    expect(screen.getByTestId('baseline-cost')).toHaveTextContent('¥10.4500');
    expect(screen.getByTestId('actual-cost')).toHaveTextContent('¥1.5500');
    expect(screen.getByTestId('burn-rate')).toHaveTextContent('¥0.42 / min');
    expect(screen.getByTestId('guard-status')).toHaveTextContent('✓ 正常护航');
  });

  it('renders soft warning alert banner when budget threshold is approached', () => {
    const warningEval: BudgetGuardEvaluation = {
      status: 'SOFT_WARNING',
      current_cost_rmb: 7.5,
      current_burn_rate_rmb_min: 1.5,
      current_tokens: 60_000,
      is_paused: false,
      reason: '已达到软预警线 ¥7.00 (70% 水位)',
      suggested_action: '请关注任务进展，必要时提前结束',
    };

    render(
      <CacheSavingsRoiHUD
        metrics={mockMetrics}
        guardEvaluation={warningEval}
      />
    );

    expect(screen.getByTestId('guard-status')).toHaveTextContent('⚠️ 软预警');
    expect(screen.getByTestId('guard-alert-box')).toBeInTheDocument();
    expect(screen.getByText(/已达到软预警线/)).toBeInTheDocument();
  });

  it('renders circuit breaker tripped banner and calls resume callback', () => {
    const handleTogglePause = vi.fn();
    const handleAdjustBudget = vi.fn();

    const trippedEval: BudgetGuardEvaluation = {
      status: 'CIRCUIT_BREAKER_TRIPPED',
      current_cost_rmb: 10.5,
      current_burn_rate_rmb_min: 3.2,
      current_tokens: 120_000,
      is_paused: true,
      reason: '单任务成本累计达 ¥10.50，触发硬预算熔断限额',
      suggested_action: '任务已被保护性自动挂起',
    };

    render(
      <CacheSavingsRoiHUD
        metrics={mockMetrics}
        guardEvaluation={trippedEval}
        onTogglePause={handleTogglePause}
        onAdjustBudget={handleAdjustBudget}
      />
    );

    expect(screen.getByTestId('guard-status')).toHaveTextContent('🛑 熔断刹车');
    expect(screen.getByText(/触发硬预算熔断限额/)).toBeInTheDocument();

    // 点击强制放行恢复
    fireEvent.click(screen.getByTestId('resume-execution-btn'));
    expect(handleTogglePause).toHaveBeenCalledWith(false);

    // 点击追加配额
    fireEvent.click(screen.getByTestId('adjust-budget-btn'));
    expect(handleAdjustBudget).toHaveBeenCalled();
  });

  it('opens and closes cost drift explainer drawer on button click', () => {
    render(
      <CacheSavingsRoiHUD
        metrics={mockMetrics}
        driftAlert={mockDriftAlert}
      />
    );

    const openBtn = screen.getByTestId('open-drift-drawer-btn');
    expect(openBtn).toBeInTheDocument();

    // 点击打开抽屉
    fireEvent.click(openBtn);
    expect(screen.getByTestId('cost-drift-drawer')).toBeInTheDocument();
    expect(screen.getByText('周期单位成本漂移感知')).toBeInTheDocument();
    expect(screen.getByTestId('drift-category')).toHaveTextContent('code_refactoring');
    expect(screen.getByTestId('drift-model')).toHaveTextContent('deepseek-chat');
    expect(screen.getByTestId('current-unit-cost')).toHaveTextContent('¥0.0250');
    expect(screen.getByTestId('baseline-unit-cost')).toHaveTextContent('¥0.0100');
    expect(screen.getByTestId('drift-percentage')).toHaveTextContent('+150%');
    expect(screen.getByTestId('drift-reason-badge')).toHaveTextContent('缓存击穿劣化');
    expect(screen.getByTestId('drift-explanation')).toHaveTextContent(/Prompt 缓存击穿劣化/);

    // 点击关闭抽屉
    fireEvent.click(screen.getByTestId('drawer-close-btn'));
    expect(screen.queryByTestId('cost-drift-drawer')).not.toBeInTheDocument();
  });
});
