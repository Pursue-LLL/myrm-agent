import { describe, expect, it, beforeEach } from 'vitest';
import { useProgressiveBootStore } from '../useProgressiveBootStore';

describe('useProgressiveBootStore', () => {
  beforeEach(() => {
    useProgressiveBootStore.getState().resetBootState();
  });

  it('初始状态为 minimal 档位，包含 5 项全部就绪的静默后台服务', () => {
    const state = useProgressiveBootStore.getState();
    expect(state.tier).toBe('minimal');
    expect(state.isDrawerOpen).toBe(false);
    expect(state.services.length).toBe(5);
    expect(state.services.every((s) => s.isReady)).toBe(true);
    expect(state.silencedNotices).toEqual([]);
  });

  it('可以自由切换披露档位与开关抽屉', () => {
    const store = useProgressiveBootStore.getState();
    store.setDisclosureTier('expert');
    expect(useProgressiveBootStore.getState().tier).toBe('expert');

    store.toggleDrawer(true);
    expect(useProgressiveBootStore.getState().isDrawerOpen).toBe(true);

    store.toggleDrawer(false);
    expect(useProgressiveBootStore.getState().isDrawerOpen).toBe(false);
  });

  it('阻断弹窗拦截器能够将侵入式通知转化为静默通知，并支持单项关闭', () => {
    const store = useProgressiveBootStore.getState();
    const noticeId = store.suppressBlockingModal({
      title: '强制更新提示',
      source: 'UpdateChecker',
      severity: 'warning',
      details: '检测到最新补丁包',
    });

    const updated = useProgressiveBootStore.getState();
    expect(updated.silencedNotices.length).toBe(1);
    expect(updated.silencedNotices[0].id).toBe(noticeId);
    expect(updated.silencedNotices[0].title).toBe('强制更新提示');

    // 关闭通知
    store.dismissNotice(noticeId);
    expect(useProgressiveBootStore.getState().silencedNotices).toEqual([]);
  });

  it('能够更新特定后台服务的探活状态与延迟', () => {
    const store = useProgressiveBootStore.getState();
    store.updateServiceStatus('srv_sandbox', false, 120);

    const srv = useProgressiveBootStore
      .getState()
      .services.find((s) => s.id === 'srv_sandbox');
    expect(srv?.isReady).toBe(false);
    expect(srv?.latencyMs).toBe(120);
  });
});
