/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/budgetPacking::getDefaultBudget, packRecallCandidates
 * ../command-center/BudgetGreedyPackingStudioCard::BudgetGreedyPackingStudioCard
 *
 * [OUTPUT]
 * Test suite verifying Budget Greedy Marginal Value Recall Packing Studio Card (Item 122 P2):
 * 1. Default render of card header, badges, and 4-dimension HUD telemetry bar
 * 2. Tab switching between Marginal Value Packing view and Token Accounting tuner view
 * 3. Repack candidates interaction and feedback banner
 * 4. Token accounting parameter simulation interaction
 * 5. Reset to default budget configuration interaction
 *
 * [POS]
 * Unit test for Item 122.
 * Strict typing applied: No `any` types allowed. File lines < 300.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BudgetGreedyPackingStudioCard } from '../command-center/BudgetGreedyPackingStudioCard';
import {
  FALLBACK_BUDGET,
  FALLBACK_PACKED_RESULT,
} from '../command-center/budgetPackingFallbacks';

const { mockGetDefaultBudget, mockPackRecallCandidates } = vi.hoisted(() => ({
  mockGetDefaultBudget: vi.fn(),
  mockPackRecallCandidates: vi.fn(),
}));

vi.mock('@/services/memory/budgetPacking', () => ({
  getDefaultBudget: mockGetDefaultBudget,
  packRecallCandidates: mockPackRecallCandidates,
}));

describe('BudgetGreedyPackingStudioCard (Item 122 P2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetDefaultBudget.mockResolvedValue(FALLBACK_BUDGET);
    mockPackRecallCandidates.mockResolvedValue(FALLBACK_PACKED_RESULT);
  });

  it('renders default header, badges, and 4-dimension HUD telemetry bar', async () => {
    render(<BudgetGreedyPackingStudioCard />);

    expect(
      screen.getByText('预算贪心边际价值召回装箱中枢'),
    ).toBeInTheDocument();
    expect(screen.getByText('Item 122 · P2')).toBeInTheDocument();
    expect(
      screen.getByText('对标 Mnemosyne · 贪心背包算法'),
    ).toBeInTheDocument();

    // 验证 HUD 4 维指标
    expect(screen.getByText('预算填满率 (Billed Tokens)')).toBeInTheDocument();
    expect(screen.getByText(/87.5%/)).toBeInTheDocument();
    expect(screen.getByText('平均边际价值密度 (MVD)')).toBeInTheDocument();
    expect(screen.getByText(/0.0264/)).toBeInTheDocument();
    expect(screen.getByText('存储 Token 离线节省')).toBeInTheDocument();
    expect(screen.getByText('224')).toBeInTheDocument();
    expect(screen.getByText('语义冗余拦截')).toBeInTheDocument();
    expect(screen.getByText('36')).toBeInTheDocument();

    // 默认展示装箱看板内容
    await waitFor(() => {
      expect(
        screen.getByText(/贪心边际价值装箱（Marginal Value Density Knapsack）原理/),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/入选装箱记忆片段/)).toBeInTheDocument();
    expect(screen.getByText(/淘汰与抑制片段/)).toBeInTheDocument();
  });

  it('switches between Packing View and Accounting Tuner tabs smoothly', async () => {
    render(<BudgetGreedyPackingStudioCard />);

    await waitFor(() => {
      expect(
        screen.getByText(/贪心边际价值装箱（Marginal Value Density Knapsack）原理/),
      ).toBeInTheDocument();
    });

    // 切换到双轨计量与调优台
    const accountingTabBtn = screen.getByRole('button', {
      name: '切换至双轨计量与调优台',
    });
    fireEvent.click(accountingTabBtn);

    expect(
      screen.getByText('双轨 Token 计量哲学：计费 Token ≠ 存储 Token'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('双轨 Token 成本与效益审计报告'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('贪心背包调优控制台'),
    ).toBeInTheDocument();

    // 切回边际价值装箱看板
    const packingTabBtn = screen.getByRole('button', {
      name: '切换至边际价值装箱看板',
    });
    fireEvent.click(packingTabBtn);

    expect(
      screen.getByText(/贪心边际价值装箱（Marginal Value Density Knapsack）原理/),
    ).toBeInTheDocument();
  });

  it('handles repack interaction and updates feedback banner', async () => {
    render(<BudgetGreedyPackingStudioCard />);

    await waitFor(() => {
      expect(
        screen.getByText(/贪心边际价值装箱（Marginal Value Density Knapsack）原理/),
      ).toBeInTheDocument();
    });

    const repackBtn = screen.getByRole('button', {
      name: '重新触发贪心装箱',
    });
    fireEvent.click(repackBtn);

    await waitFor(() => {
      expect(mockPackRecallCandidates).toHaveBeenCalledTimes(2); // 1 on mount, 1 on click
      expect(
        screen.getByText(/贪心装箱重算完成：入选 3 条，预算填满率 87.5%/),
      ).toBeInTheDocument();
    });
  });

  it('allows token accounting simulation and updates parameters', async () => {
    render(<BudgetGreedyPackingStudioCard />);

    await waitFor(() => {
      expect(
        screen.getByText(/贪心边际价值装箱（Marginal Value Density Knapsack）原理/),
      ).toBeInTheDocument();
    });

    // 切换到调优台
    fireEvent.click(
      screen.getByRole('button', { name: '切换至双轨计量与调优台' }),
    );

    const simulateBtn = screen.getByRole('button', {
      name: '执行双轨装箱模拟计算',
    });
    fireEvent.click(simulateBtn);

    await waitFor(() => {
      expect(mockPackRecallCandidates).toHaveBeenCalled();
      expect(
        screen.getByText(/装箱参数已生效：计费消费/),
      ).toBeInTheDocument();
    });
  });

  it('resets budget configuration to defaults via HUD reset button', async () => {
    render(<BudgetGreedyPackingStudioCard />);

    const resetBtn = screen.getByRole('button', {
      name: '恢复推荐预算配置',
    });
    fireEvent.click(resetBtn);

    await waitFor(() => {
      expect(screen.getByText('已重置为系统推荐预算配置')).toBeInTheDocument();
    });
  });
});
