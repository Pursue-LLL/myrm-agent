import { describe, it, expect, beforeEach } from 'vitest';
import { useCommandCenterStore } from '../useCommandCenterStore';

describe('useCommandCenterStore', () => {
  beforeEach(() => {
    useCommandCenterStore.getState().resetStore();
  });

  it('初始状态应处于关闭状态且具备默认的 Tab 和示范数据', () => {
    const state = useCommandCenterStore.getState();
    expect(state.isOpen).toBe(false);
    expect(state.activeTab).toBe('sessions');
    expect(state.sessions.length).toBeGreaterThanOrEqual(4);
    expect(state.health.status).toBe('healthy');
    expect(state.usageHorizon).toBe(7);
  });

  it('openModal 与 closeModal 应正确管理开关与活动 Tab', () => {
    useCommandCenterStore.getState().openModal('system');
    expect(useCommandCenterStore.getState().isOpen).toBe(true);
    expect(useCommandCenterStore.getState().activeTab).toBe('system');

    useCommandCenterStore.getState().closeModal();
    expect(useCommandCenterStore.getState().isOpen).toBe(false);
  });

  it('togglePinSession 应正确切换指定会话的置顶状态', () => {
    const firstSession = useCommandCenterStore.getState().sessions[0];
    const initialPin = firstSession.isPinned;

    useCommandCenterStore.getState().togglePinSession(firstSession.id);
    const updated = useCommandCenterStore
      .getState()
      .sessions.find((s) => s.id === firstSession.id);
    expect(updated?.isPinned).toBe(!initialPin);
  });

  it('exportSessionAuditPack 应打包会话并写入 exportedAuditPack 状态', () => {
    const firstSession = useCommandCenterStore.getState().sessions[0];
    const pack = useCommandCenterStore.getState().exportSessionAuditPack(firstSession.id);

    expect(pack).not.toBeNull();
    expect(pack?.sessionId).toBe(firstSession.id);
    expect(useCommandCenterStore.getState().exportedAuditPack?.sessionId).toBe(
      firstSession.id
    );
  });

  it('setUsageHorizon 应动态切换天数跨度与用量摘要', () => {
    useCommandCenterStore.getState().setUsageHorizon(30);
    expect(useCommandCenterStore.getState().usageHorizon).toBe(30);
    expect(useCommandCenterStore.getState().usageSummary.horizonDays).toBe(30);
  });

  it('generateDebugShare 应返回脱敏 JSON 字符串', () => {
    const bundle = useCommandCenterStore.getState().generateDebugShare();
    expect(bundle).toContain('gatewayHealth');
    expect(useCommandCenterStore.getState().debugSharePayload).toBe(bundle);
  });
});
