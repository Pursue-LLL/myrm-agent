import { beforeEach, describe, expect, it } from 'vitest';
import { useArtifactSandboxStore } from '../useArtifactSandboxStore';
import type { FinancialShockScenario, InteractiveArtifactItem } from '../artifactSandboxTypes';

describe('useArtifactSandboxStore', () => {
  beforeEach(() => {
    useArtifactSandboxStore.getState().resetAll();
  });

  it('初始状态规范且支持重置', () => {
    const state = useArtifactSandboxStore.getState();
    expect(state.sandboxMode).toBe('rich_newsletter');
    expect(state.activeTheme).toBe('mint_breeze');
    expect(state.isFullscreen).toBe(false);
    expect(state.activeShock).toBeNull();
  });

  it('支持切换活动工件并联动更新沙盒模式与排版主题', () => {
    const item: InteractiveArtifactItem = {
      id: 'art-2',
      title: '贪吃蛇 H5 小游戏',
      mode: 'html_live',
      rawContent: '<canvas id="game"></canvas>',
      theme: 'cyber_blue',
      updatedAt: Date.now(),
    };

    useArtifactSandboxStore.getState().setActiveArtifact(item);
    const state = useArtifactSandboxStore.getState();
    expect(state.activeArtifact?.id).toBe('art-2');
    expect(state.sandboxMode).toBe('html_live');
    expect(state.activeTheme).toBe('cyber_blue');
  });

  it('支持切换排版主题与全屏状态', () => {
    const store = useArtifactSandboxStore.getState();
    store.setActiveTheme('executive_noir');
    expect(useArtifactSandboxStore.getState().activeTheme).toBe('executive_noir');

    store.toggleFullscreen();
    expect(useArtifactSandboxStore.getState().isFullscreen).toBe(true);
    store.toggleFullscreen(false);
    expect(useArtifactSandboxStore.getState().isFullscreen).toBe(false);
  });

  it('修改基础金融参数或注入宏观冲击时自动更新推演结果', () => {
    const initialMargin =
      useArtifactSandboxStore.getState().computedFinancialMetrics.projectedProfitMargin;

    // 提高下游需求
    useArtifactSandboxStore.getState().setBaseFinancialMetrics({
      downstreamEndUserDemand: 160,
    });

    const newMargin =
      useArtifactSandboxStore.getState().computedFinancialMetrics.projectedProfitMargin;
    expect(newMargin).toBeGreaterThan(initialMargin);

    // 注入断供冲击
    const shock: FinancialShockScenario = {
      id: 'shock-test',
      name: '测试冲击',
      description: '冲击测试',
      impactDeltas: {
        upstreamRawMaterialCost: 50,
      },
    };
    useArtifactSandboxStore.getState().applyShockScenario(shock);
    expect(useArtifactSandboxStore.getState().activeShock).toEqual(shock);

    const shockedMargin =
      useArtifactSandboxStore.getState().computedFinancialMetrics.projectedProfitMargin;
    expect(shockedMargin).toBeLessThan(newMargin);
  });
});
