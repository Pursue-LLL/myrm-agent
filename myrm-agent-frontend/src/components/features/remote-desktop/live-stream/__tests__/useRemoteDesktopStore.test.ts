import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useRemoteDesktopStore } from '../useRemoteDesktopStore';

describe('useRemoteDesktopStore Zustand state store', () => {
  beforeEach(() => {
    useRemoteDesktopStore.getState().resetState();
  });

  it('initializes with default streaming state and observer mode', () => {
    const state = useRemoteDesktopStore.getState();
    expect(state.connectionState).toBe('streaming');
    expect(state.controlMode).toBe('observer');
    expect(state.sandboxId).toBe('sandbox-cloud-vm-8891');
    expect(state.isShareModalOpen).toBe(false);
    expect(state.currentTicket).toBeNull();
    expect(state.isTakeoverAlertActive).toBe(false);
    expect(state.actionHistory.length).toBeGreaterThanOrEqual(3);
  });

  it('handles pause, resume and disconnect stream lifecycle', () => {
    const store = useRemoteDesktopStore.getState();

    store.pauseStream();
    expect(useRemoteDesktopStore.getState().connectionState).toBe('paused');

    store.resumeStream();
    expect(useRemoteDesktopStore.getState().connectionState).toBe('streaming');

    store.disconnectStream();
    expect(useRemoteDesktopStore.getState().connectionState).toBe('disconnected');
  });

  it('handles async connectStream with updated sandboxId', async () => {
    const store = useRemoteDesktopStore.getState();
    const connectPromise = store.connectStream('sandbox-custom-404');

    expect(useRemoteDesktopStore.getState().connectionState).toBe('connecting');
    expect(useRemoteDesktopStore.getState().sandboxId).toBe('sandbox-custom-404');

    await connectPromise;
    expect(useRemoteDesktopStore.getState().connectionState).toBe('streaming');
    expect(useRemoteDesktopStore.getState().controlMode).toBe('observer');
  });

  it('triggers human takeover and dispatches global event', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    useRemoteDesktopStore.getState().requestHumanTakeover('检测到极验滑动验证码');
    const takeoverState = useRemoteDesktopStore.getState();

    expect(takeoverState.controlMode).toBe('human-takeover');
    expect(takeoverState.isTakeoverAlertActive).toBe(true);
    expect(takeoverState.takeoverReason).toBe('检测到极验滑动验证码');
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'myrm:remote-desktop-takeover-changed',
      })
    );

    useRemoteDesktopStore.getState().releaseHumanTakeover();
    const releasedState = useRemoteDesktopStore.getState();

    expect(releasedState.controlMode).toBe('observer');
    expect(releasedState.isTakeoverAlertActive).toBe(false);
    expect(releasedState.takeoverReason).toBeNull();

    dispatchSpy.mockRestore();
  });

  it('manages ephemeral share modal state and ticket issuance event', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    useRemoteDesktopStore.getState().openShareModal();
    expect(useRemoteDesktopStore.getState().isShareModalOpen).toBe(true);
    expect(useRemoteDesktopStore.getState().currentTicket).not.toBeNull();

    const newTicket = useRemoteDesktopStore.getState().createShareTicket({
      ttlSeconds: 86400,
      allowTakeover: true,
      oneTimeOnly: true,
    });

    expect(newTicket.allowTakeover).toBe(true);
    expect(newTicket.oneTimeOnly).toBe(true);
    expect(useRemoteDesktopStore.getState().currentTicket?.ticketId).toBe(newTicket.ticketId);
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'myrm:ephemeral-share-created',
      })
    );

    useRemoteDesktopStore.getState().closeShareModal();
    expect(useRemoteDesktopStore.getState().isShareModalOpen).toBe(false);

    dispatchSpy.mockRestore();
  });

  it('toggles window expansion and records action telemetry history', () => {
    expect(useRemoteDesktopStore.getState().isExpanded).toBe(false);
    useRemoteDesktopStore.getState().toggleExpanded();
    expect(useRemoteDesktopStore.getState().isExpanded).toBe(true);

    useRemoteDesktopStore.getState().pushActionTelemetry({
      actionType: 'click',
      description: '点击下载分析报表按钮',
      coordinates: { x: 800, y: 600 },
    });

    const latest = useRemoteDesktopStore.getState().actionHistory[0];
    expect(latest.actionType).toBe('click');
    expect(latest.description).toBe('点击下载分析报表按钮');
    expect(latest.coordinates).toEqual({ x: 800, y: 600 });
  });
});
