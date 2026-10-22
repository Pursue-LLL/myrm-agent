import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useMobilePairingQrGateway } from '../useMobilePairingQrGateway';

describe('useMobilePairingQrGateway', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('initializes pairing session on initiatePairing with waiting_scan stage', () => {
    const { result } = renderHook(() => useMobilePairingQrGateway({ defaultChannel: 'feishu', expirySeconds: 60 }));

    expect(result.current.session).toBeNull();
    expect(result.current.companion).toBeNull();

    act(() => {
      result.current.initiatePairing('feishu');
    });

    expect(result.current.session).not.toBeNull();
    expect(result.current.session?.stage).toBe('waiting_scan');
    expect(result.current.session?.channel).toBe('feishu');
    expect(result.current.session?.qrPayload).toContain('myrm://pair');
    expect(result.current.remainingSeconds).toBe(60);
  });

  it('switches channel and generates new ephemeral pairing session', () => {
    const { result } = renderHook(() => useMobilePairingQrGateway({ defaultChannel: 'feishu' }));

    act(() => {
      result.current.initiatePairing('dingtalk');
    });

    expect(result.current.activeChannel).toBe('dingtalk');
    expect(result.current.session?.channel).toBe('dingtalk');
  });

  it('transitions stage to expired when countdown reaches zero', () => {
    const { result } = renderHook(() => useMobilePairingQrGateway({ expirySeconds: 5 }));

    act(() => {
      result.current.initiatePairing('wechat_work');
    });

    expect(result.current.remainingSeconds).toBe(5);

    act(() => {
      vi.advanceTimersByTime(5000);
    });

    expect(result.current.remainingSeconds).toBe(0);
    expect(result.current.session?.stage).toBe('expired');
  });

  it('refreshes QR and resets countdown on refreshQr', () => {
    const { result } = renderHook(() => useMobilePairingQrGateway({ expirySeconds: 10 }));

    act(() => {
      result.current.initiatePairing('feishu');
    });

    act(() => {
      vi.advanceTimersByTime(6000);
    });
    expect(result.current.remainingSeconds).toBe(4);

    act(() => {
      result.current.refreshQr();
    });

    expect(result.current.remainingSeconds).toBe(10);
    expect(result.current.session?.stage).toBe('waiting_scan');
  });

  it('completes pairing and establishes companion connection via simulateScanAndAuth', () => {
    const { result } = renderHook(() => useMobilePairingQrGateway());

    act(() => {
      result.current.initiatePairing('feishu');
    });

    act(() => {
      result.current.simulateScanAndAuth('Android Pixel 9 (离线管家)');
    });

    expect(result.current.session?.stage).toBe('authenticated');
    expect(result.current.session?.deviceLabel).toBe('Android Pixel 9 (离线管家)');
    expect(result.current.companion).not.toBeNull();
    expect(result.current.companion?.isOnline).toBe(true);

    // Disconnect
    act(() => {
      result.current.disconnectCompanion();
    });

    expect(result.current.companion).toBeNull();
    expect(result.current.session?.stage).toBe('waiting_scan');
  });
});
