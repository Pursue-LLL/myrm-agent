import { describe, it, expect, beforeEach } from 'vitest';
import { useMobileCompanionStore } from '../useMobileCompanionStore';

describe('useMobileCompanionStore', () => {
  beforeEach(() => {
    useMobileCompanionStore.getState().reset();
  });

  it('初始状态规范合规并挂载默认活跃任务', () => {
    const state = useMobileCompanionStore.getState();
    expect(state.isPairingModalOpen).toBe(false);
    expect(state.pairingConfig).toBeNull();
    expect(state.activeTask).not.toBeNull();
    expect(state.activeTask?.phase).toBe('testing');
    expect(state.isConnected).toBe(true);
    expect(state.isRemoteSteeringOpen).toBe(false);
    expect(state.sentSteeringCommands).toEqual([]);
  });

  it('支持呼出与关闭配对二维码模态框', () => {
    const store = useMobileCompanionStore.getState();
    store.openPairingModal('sess-custom-999');

    const stateOpened = useMobileCompanionStore.getState();
    expect(stateOpened.isPairingModalOpen).toBe(true);
    expect(stateOpened.pairingConfig?.sessionId).toBe('sess-custom-999');
    expect(stateOpened.pairingConfig?.pairingUrl).toContain('sess-custom-999');

    store.closePairingModal();
    expect(useMobileCompanionStore.getState().isPairingModalOpen).toBe(false);
  });

  it('支持更新任务快照 (updateTaskSnapshot)', () => {
    const store = useMobileCompanionStore.getState();
    store.updateTaskSnapshot({
      progress: 90,
      phase: 'deploying',
      estimatedSecondsRemaining: 30,
    });

    const state = useMobileCompanionStore.getState();
    expect(state.activeTask?.progress).toBe(90);
    expect(state.activeTask?.phase).toBe('deploying');
    expect(state.activeTask?.estimatedSecondsRemaining).toBe(30);
  });

  it('支持手机端批准与拒绝待审批高危操作', () => {
    const store = useMobileCompanionStore.getState();

    // 1. 批准操作
    store.approvePendingAction(true);
    let state = useMobileCompanionStore.getState();
    expect(state.activeTask?.pendingApproval).toBeUndefined();
    expect(state.activeTask?.highSnrSummary.some((l) => l.includes('手机端批准'))).toBe(true);

    // 2. 重新注入一个待审批项后拒绝
    store.updateTaskSnapshot({
      pendingApproval: {
        id: 'appr-2',
        toolName: 'rm_rf_sandbox',
        description: '删除沙箱临时文件夹',
        riskLevel: 'high',
        params: {},
      },
    });

    store.approvePendingAction(false, '风险过高，暂不清理');
    state = useMobileCompanionStore.getState();
    expect(state.activeTask?.pendingApproval).toBeUndefined();
    expect(state.activeTask?.phase).toBe('paused_approval');
    expect(
      state.activeTask?.highSnrSummary.some((l) => l.includes('手机端拒绝') && l.includes('风险过高'))
    ).toBe(true);
  });

  it('支持发送手机端随行远程微调指令 (sendRemoteSteering)', () => {
    const store = useMobileCompanionStore.getState();
    store.sendRemoteSteering('加个下载 PDF 报价单按钮');

    const state = useMobileCompanionStore.getState();
    expect(state.sentSteeringCommands).toContain('加个下载 PDF 报价单按钮');
    expect(
      state.activeTask?.highSnrSummary.some((l) => l.includes('随行微调已回传'))
    ).toBe(true);
    expect(state.isRemoteSteeringOpen).toBe(false);
  });
});
