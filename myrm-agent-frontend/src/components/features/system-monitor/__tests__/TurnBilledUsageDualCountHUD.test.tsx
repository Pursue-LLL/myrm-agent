import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TurnBilledUsageDualCountHUD } from '../TurnBilledUsageDualCountHUD';
import type { TurnUsageSummaryData } from '../turnUsageTypes';

describe('TurnBilledUsageDualCountHUD', () => {
  const mockSummary: TurnUsageSummaryData = {
    session_id: 'sess_test_100',
    turn_id: 'turn_test_200',
    rounds_count: 3,
    billed: {
      input_tokens: 1450,
      output_tokens: 650,
      cache_read: 1800,
      cache_write: 1000,
    },
    freeze_usage: {
      input_tokens: 1450,
      output_tokens: 650,
      cache_read: 1000,
      cache_write: 0,
    },
    cache_divergence_tokens: 1800, // (1800 + 1000) - (1000 + 0) = 1800
    created_at: '2026-10-12T15:00:00Z',
    updated_at: '2026-10-12T15:05:00Z',
  };

  it('renders dual count HUD with session info, billed vs freeze cards, and divergence callout', () => {
    const onRefresh = vi.fn();
    const onSimulateRound = vi.fn();

    render(
      <TurnBilledUsageDualCountHUD
        summary={mockSummary}
        onRefresh={onRefresh}
        onSimulateRound={onSimulateRound}
      />
    );

    // 标题与核心概念
    expect(
      screen.getByText('回合级使用量双计数透视 HUD (Turn Billed Usage Dual Count)')
    ).toBeInTheDocument();
    expect(screen.getByText('Bill 与 Freeze 物理隔离')).toBeInTheDocument();

    // 会话与回合标识
    expect(screen.getByText('sess_test_100')).toBeInTheDocument();
    expect(screen.getByText('turn_test_200')).toBeInTheDocument();
    expect(screen.getByText('3 轮')).toBeInTheDocument();

    // Billed 累加卡片
    expect(
      screen.getByText('真实账单累计 (The Bill · summed_with)')
    ).toBeInTheDocument();
    // billedTotal = 1450 + 650 + 1800 + 1000 = 4900
    expect(screen.getByText('4,900')).toBeInTheDocument();

    // Freeze 缓存决策卡片
    expect(
      screen.getByText('缓存冻结状态 (The Freeze · merged_with)')
    ).toBeInTheDocument();
    // freezeTotal = 1450 + 650 + 1000 + 0 = 3100
    expect(screen.getByText('3,100')).toBeInTheDocument();

    // 缓存读分离对比：Billed 中的 1,800 与 Freeze 中的 1,000
    expect(screen.getAllByText('1,800').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('1,000').length).toBeGreaterThanOrEqual(2);

    // 防虚假膨胀隔离保护
    expect(
      screen.getByText('防膨胀隔离保护生效中 (Anti-Inflation Shield)')
    ).toBeInTheDocument();
    expect(screen.getByText('1,800 Tokens')).toBeInTheDocument();

    // 按钮交互
    const refreshBtn = screen.getByText('刷新数据');
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);

    const simBtn = screen.getByText('模拟单轮再驱动 (+Round)');
    fireEvent.click(simBtn);
    expect(onSimulateRound).toHaveBeenCalledTimes(1);
  });
});
