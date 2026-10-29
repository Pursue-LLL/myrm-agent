import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FinancialSandplayWidget } from '../FinancialSandplayWidget';
import { useArtifactSandboxStore } from '../useArtifactSandboxStore';

describe('FinancialSandplayWidget', () => {
  beforeEach(() => {
    useArtifactSandboxStore.getState().resetAll();
  });

  it('正常渲染产业链沙盘指标看板、滑块与宏观冲击情景卡片', () => {
    render(<FinancialSandplayWidget />);
    expect(
      screen.getByTestId('financial-sandplay-widget')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('upstream-cost-slider')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('midstream-capacity-slider')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('downstream-demand-slider')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('projected-margin-card')
    ).toBeInTheDocument();
    expect(screen.getByTestId('risk-index-card')).toBeInTheDocument();
  });

  it('支持拖动滑块调节上中下游产业链参数', () => {
    render(<FinancialSandplayWidget />);
    const demandSlider = screen.getByTestId(
      'downstream-demand-slider'
    ) as HTMLInputElement;

    fireEvent.change(demandSlider, { target: { value: '180' } });
    expect(
      useArtifactSandboxStore.getState().baseFinancialMetrics
        .downstreamEndUserDemand
    ).toBe(180);
  });

  it('点击宏观冲击情景卡片，注入冲击并触发指标重算', () => {
    const handleScenarioChange = vi.fn();
    render(
      <FinancialSandplayWidget onScenarioChange={handleScenarioChange} />
    );

    const bottleneckBtn = screen.getByTestId(
      'scenario-btn-supply_bottleneck'
    );
    fireEvent.click(bottleneckBtn);

    expect(handleScenarioChange).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'supply_bottleneck',
      })
    );
    expect(useArtifactSandboxStore.getState().activeShock?.id).toBe(
      'supply_bottleneck'
    );

    // 再次点击取消情景
    fireEvent.click(bottleneckBtn);
    expect(handleScenarioChange).toHaveBeenCalledWith(null);
    expect(useArtifactSandboxStore.getState().activeShock).toBeNull();
  });

  it('点击重置参数按钮，清空冲击并恢复默认基准指标', () => {
    useArtifactSandboxStore.getState().setBaseFinancialMetrics({
      upstreamRawMaterialCost: 180,
    });
    useArtifactSandboxStore.getState().applyShockScenario({
      id: 'test',
      name: 'test',
      description: 'test',
      impactDeltas: {},
    });

    render(<FinancialSandplayWidget />);

    const resetBtn = screen.getByTestId('sandplay-reset-btn');
    fireEvent.click(resetBtn);

    const state = useArtifactSandboxStore.getState();
    expect(state.baseFinancialMetrics.upstreamRawMaterialCost).toBe(100);
    expect(state.activeShock).toBeNull();
  });
});
