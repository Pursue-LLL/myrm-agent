import { describe, it, expect, beforeEach } from 'vitest';
import { useThemeLayerInvariantStore } from '../useThemeLayerInvariantStore';

describe('useThemeLayerInvariantStore', () => {
  beforeEach(() => {
    useThemeLayerInvariantStore.getState().reset();
  });

  it('初始状态具备默认预烘基线且当前评测报告为空', () => {
    const state = useThemeLayerInvariantStore.getState();
    expect(state.currentReport).toBeNull();
    expect(state.selectedBaseline?.baselineVersion).toBe('v0.9.0-clean');
    expect(state.isBaselineModalOpen).toBe(false);
    expect(state.prebakedBaselines.length).toBeGreaterThanOrEqual(2);
  });

  it('evaluateCurrentTheme 能够完成双主题同帧评测并生成基线对比结果', () => {
    const store = useThemeLayerInvariantStore.getState();
    const report = store.evaluateCurrentTheme(
      '#ffffff',
      '#ffffff',
      '#09090b',
      '#18181b'
    );

    expect(report.allPassed).toBe(true);
    expect(report.lightEvaluation.isInvariantSatisfied).toBe(true);
    expect(report.darkEvaluation.isInvariantSatisfied).toBe(true);
    expect(report.baselineComparison?.hasRegression).toBe(false);

    expect(useThemeLayerInvariantStore.getState().currentReport).toBe(report);
  });

  it('支持切换预烘基线版本并自动重新触发回归比对', () => {
    const store = useThemeLayerInvariantStore.getState();
    // 先产生一个浅色发灰违规的评测报告
    store.evaluateCurrentTheme('#ffffff', '#e7e7e8', '#09090b', '#18181b');

    // 默认比对 v0.9.0-clean（合规基线）会有回归
    expect(
      useThemeLayerInvariantStore.getState().currentReport?.baselineComparison
        ?.hasRegression
    ).toBe(true);

    // 切换到另一个同样有发灰缺陷的旧版本基线 v0.10.0-recessed-buggy
    const buggyBaseline = store.prebakedBaselines.find(
      (b) => b.baselineVersion === 'v0.10.0-recessed-buggy'
    );
    expect(buggyBaseline).toBeDefined();

    if (buggyBaseline) {
      store.selectBaseline(buggyBaseline);
    }
    // 因为基线本身也是发灰缺陷，所以比对时不再判定为新增回归
    expect(
      useThemeLayerInvariantStore.getState().currentReport?.baselineComparison
        ?.hasRegression
    ).toBe(false);
  });

  it('toggleBaselineModal 能够正确切换基线对比弹窗的显示状态', () => {
    const store = useThemeLayerInvariantStore.getState();
    store.toggleBaselineModal(true);
    expect(useThemeLayerInvariantStore.getState().isBaselineModalOpen).toBe(
      true
    );

    store.toggleBaselineModal(false);
    expect(useThemeLayerInvariantStore.getState().isBaselineModalOpen).toBe(
      false
    );
  });

  it('applyQuickThemeFix 能够一键修复浅色发灰缺陷并恢复双主题合格状态', () => {
    const store = useThemeLayerInvariantStore.getState();
    // 载入浅色违规主题
    store.evaluateCurrentTheme('#ffffff', '#e7e7e8', '#09090b', '#18181b');
    expect(
      useThemeLayerInvariantStore.getState().currentReport?.allPassed
    ).toBe(false);

    // 执行浅色快速修复
    store.applyQuickThemeFix('light');

    const fixedReport = useThemeLayerInvariantStore.getState().currentReport;
    expect(fixedReport?.allPassed).toBe(true);
    expect(fixedReport?.lightEvaluation.cardHex).toBe('#ffffff');
    expect(fixedReport?.lightEvaluation.isInvariantSatisfied).toBe(true);
  });

  it('调用 reset 能够彻底还原所有状态', () => {
    const store = useThemeLayerInvariantStore.getState();
    store.evaluateCurrentTheme('#ffffff', '#e7e7e8', '#09090b', '#18181b');
    store.toggleBaselineModal(true);

    store.reset();
    const state = useThemeLayerInvariantStore.getState();
    expect(state.currentReport).toBeNull();
    expect(state.isBaselineModalOpen).toBe(false);
  });
});
