import { describe, it, expect, beforeEach } from 'vitest';
import { useThreeModeStore } from '../useThreeModeStore';
import { resolveModeSecurityPolicy } from '../threeModeEngine';

describe('useThreeModeStore 状态单测', () => {
  beforeEach(() => {
    useThreeModeStore.setState({
      currentMode: 'ask',
      policy: resolveModeSecurityPolicy('ask'),
      isMatrixOpen: false,
      intentGuidance: null,
      modeSwitchHistory: [],
    });
  });

  it('初始状态为 ask 模式与只读安全策略', () => {
    const state = useThreeModeStore.getState();
    expect(state.currentMode).toBe('ask');
    expect(state.policy.readOnly).toBe(true);
    expect(state.isMatrixOpen).toBe(false);
  });

  it('setMode 切换到 craft 并联动更新全自动化权限策略与流转历史', () => {
    useThreeModeStore.getState().setMode('craft');

    const state = useThreeModeStore.getState();
    expect(state.currentMode).toBe('craft');
    expect(state.policy.allowFileWrites).toBe(true);
    expect(state.policy.allowShellExecution).toBe(true);
    expect(state.modeSwitchHistory.length).toBe(1);
    expect(state.modeSwitchHistory[0].from).toBe('ask');
    expect(state.modeSwitchHistory[0].to).toBe('craft');
  });

  it('checkUserInputIntent 与 dismissIntentGuidance 控制意图气泡', () => {
    // 在 ask 模式下检测到写入意图
    const result = useThreeModeStore.getState().checkUserInputIntent('请创建文件 report.csv 并保存到磁盘');
    expect(result.hasWriteIntent).toBe(true);
    expect(useThreeModeStore.getState().intentGuidance?.suggestedMode).toBe('craft');

    // 关闭气泡
    useThreeModeStore.getState().dismissIntentGuidance();
    expect(useThreeModeStore.getState().intentGuidance).toBeNull();
  });

  it('toggleMatrix 与 closeMatrix 控制权限矩阵抽屉', () => {
    useThreeModeStore.getState().toggleMatrix();
    expect(useThreeModeStore.getState().isMatrixOpen).toBe(true);

    useThreeModeStore.getState().closeMatrix();
    expect(useThreeModeStore.getState().isMatrixOpen).toBe(false);
  });
});
