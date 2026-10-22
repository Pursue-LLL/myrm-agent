'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import TopologyPruningIndicator from '../TopologyPruningIndicator';

const translations: Record<string, string> = {
  tier1Badge: 'Tier 1 SOTA 推理',
  tier2Badge: 'Tier 2 强基模',
  tier3Badge: 'Tier 3 轻量小模',
  directFolded: '⚡ 单 Agent 深度推理',
  hybridFolded: '⚡ 混合折叠 (主干直出+审计)',
  fanoutMode: '多智能体细粒度派发',
  savedTurnsTokens: '已省 {turns} 轮 / {tokens} Token',
  strategyAuto: '自适应',
  strategyDirect: '仅单Agent',
  strategyMultiAgent: '强制多Agent',
};

const stableT = (key: string, params?: { turns?: number; tokens?: number }) => {
  let val = translations[key] ?? key;
  if (params?.turns !== undefined) {
    val = val.replace('{turns}', String(params.turns));
  }
  if (params?.tokens !== undefined) {
    val = val.replace('{tokens}', String(params.tokens));
  }
  return val;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('TopologyPruningIndicator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Tier 1 folded direct reasoning state correctly', () => {
    render(
      <TopologyPruningIndicator
        modelName="claude-3-7-sonnet"
        modelTier="tier_1_sota_reasoning"
        isFolded={true}
        decision="direct_execution"
        estimatedSavedTurns={6}
        estimatedSavedTokens={4800}
      />
    );

    expect(screen.getByTestId('topology-pruning-indicator')).toBeInTheDocument();
    expect(screen.getByText('Tier 1 SOTA 推理')).toBeInTheDocument();
    expect(screen.getByText('claude-3-7-sonnet')).toBeInTheDocument();
    expect(screen.getByText('⚡ 单 Agent 深度推理')).toBeInTheDocument();
    expect(screen.getByText('(已省 6 轮 / 4800 Token)')).toBeInTheDocument();
  });

  it('renders Tier 3 fanout mode when not folded', () => {
    render(
      <TopologyPruningIndicator
        modelName="qwen-2.5-7b"
        modelTier="tier_3_fast_light"
        isFolded={false}
        decision="fanout_multi_agent"
      />
    );

    expect(screen.getByText('Tier 3 轻量小模')).toBeInTheDocument();
    expect(screen.getByText('qwen-2.5-7b')).toBeInTheDocument();
    expect(screen.getByText('多智能体细粒度派发')).toBeInTheDocument();
  });

  it('renders hybrid folded decision label', () => {
    render(
      <TopologyPruningIndicator
        modelName="deepseek-r1"
        modelTier="tier_1_sota_reasoning"
        isFolded={true}
        decision="hybrid_folded"
        estimatedSavedTurns={6}
        estimatedSavedTokens={4800}
      />
    );

    expect(screen.getByText('⚡ 混合折叠 (主干直出+审计)')).toBeInTheDocument();
  });

  it('triggers onStrategyChange when user switches mode buttons', () => {
    const handleStrategyChange = vi.fn();
    render(
      <TopologyPruningIndicator
        modelName="claude-3-7-sonnet"
        strategy="auto"
        onStrategyChange={handleStrategyChange}
      />
    );

    const directBtn = screen.getByTestId('strategy-btn-direct');
    fireEvent.click(directBtn);
    expect(handleStrategyChange).toHaveBeenCalledWith('direct_only');

    const fanoutBtn = screen.getByTestId('strategy-btn-fanout');
    fireEvent.click(fanoutBtn);
    expect(handleStrategyChange).toHaveBeenCalledWith('always_multi_agent');

    const autoBtn = screen.getByTestId('strategy-btn-auto');
    fireEvent.click(autoBtn);
    expect(handleStrategyChange).toHaveBeenCalledWith('auto');
  });
});
