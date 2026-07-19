import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';

const fetchWithTimeout = vi.fn();
const sendMessage = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: (...args: unknown[]) => fetchWithTimeout(...args),
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({ sendMessage }),
  },
}));

vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    success: (...args: unknown[]) => toastSuccess(...args),
  },
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

describe('useBrowserTakeoverActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useBrowserTakeoverStore.getState().completeTakeover();
  });

  afterEach(() => {
    useBrowserTakeoverStore.getState().completeTakeover();
  });

  function seedTakeover(uiMode: 'managed' | 'extension' = 'managed') {
    useBrowserTakeoverStore.getState().requestTakeover({
      reason: 'Enter SMS code',
      messageId: 'msg-1',
      ui_mode: uiMode,
      url: 'https://bank.example/login',
    });
  }

  it('does not call VNC resume when extension mode completes', async () => {
    seedTakeover('extension');
    fetchWithTimeout.mockResolvedValue({ ok: true, json: async () => ({ learned: false }) });
    sendMessage.mockResolvedValue(undefined);

    const { useBrowserTakeoverActions } = await import('@/hooks/useBrowserTakeoverActions');
    const { result } = renderHook(() => useBrowserTakeoverActions());

    await act(async () => {
      await result.current.handleTakeoverComplete();
    });

    expect(fetchWithTimeout).not.toHaveBeenCalled();
    expect(sendMessage).toHaveBeenCalledWith('', 'msg-1', undefined, { action: 'completed', message: '' });
    expect(useBrowserTakeoverStore.getState().pending).toBe(false);
  });

  it('calls VNC resume when managed mode completes', async () => {
    seedTakeover('managed');
    fetchWithTimeout.mockResolvedValue({ ok: true, json: async () => ({ learned: true }) });
    sendMessage.mockResolvedValue(undefined);

    const { useBrowserTakeoverActions } = await import('@/hooks/useBrowserTakeoverActions');
    const { result } = renderHook(() => useBrowserTakeoverActions());

    await act(async () => {
      await result.current.handleTakeoverComplete();
    });

    expect(fetchWithTimeout).toHaveBeenCalledWith('/webui/vnc/resume', { method: 'POST' });
    expect(toastSuccess).toHaveBeenCalledWith('takeoverLearned', { duration: 3000 });
  });

  it('restores takeover UI when managed VNC resume HTTP fails', async () => {
    seedTakeover('managed');
    fetchWithTimeout.mockResolvedValue({ ok: false, status: 503 });

    const { useBrowserTakeoverActions } = await import('@/hooks/useBrowserTakeoverActions');
    const { result } = renderHook(() => useBrowserTakeoverActions());

    await act(async () => {
      await result.current.handleTakeoverComplete();
    });

    expect(sendMessage).not.toHaveBeenCalled();
    expect(useBrowserTakeoverStore.getState().pending).toBe(true);
    expect(useBrowserTakeoverStore.getState().uiMode).toBe('managed');
    expect(toastError).toHaveBeenCalledWith('takeoverResumeFailed');
  });

  it('restores takeover UI when complete fails after dismiss', async () => {
    seedTakeover('extension');
    sendMessage.mockRejectedValue(new Error('network'));

    const { useBrowserTakeoverActions } = await import('@/hooks/useBrowserTakeoverActions');
    const { result } = renderHook(() => useBrowserTakeoverActions());

    await act(async () => {
      await result.current.handleTakeoverComplete();
    });

    expect(useBrowserTakeoverStore.getState().pending).toBe(true);
    expect(useBrowserTakeoverStore.getState().uiMode).toBe('extension');
    expect(useBrowserTakeoverStore.getState().messageId).toBe('msg-1');
    expect(toastError).toHaveBeenCalledWith('takeoverResumeFailed');
  });

  it('restores takeover UI when skip fails after dismiss', async () => {
    seedTakeover('managed');
    fetchWithTimeout.mockResolvedValue({ ok: true, json: async () => ({ learned: false }) });
    sendMessage.mockRejectedValue(new Error('network'));

    const { useBrowserTakeoverActions } = await import('@/hooks/useBrowserTakeoverActions');
    const { result } = renderHook(() => useBrowserTakeoverActions());

    await act(async () => {
      await result.current.handleTakeoverSkip();
    });

    expect(fetchWithTimeout).toHaveBeenCalledWith('/webui/vnc/resume', { method: 'POST' });
    expect(useBrowserTakeoverStore.getState().pending).toBe(true);
    expect(useBrowserTakeoverStore.getState().uiMode).toBe('managed');
    expect(toastError).toHaveBeenCalledWith('takeoverResumeFailed');
  });
});
