import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType } from '@/store/chat/types';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import type { StreamCtx } from '../../streamContext';
import { fileDiffEvents } from '../fileDiffEvents';

const fetchWithTimeout = vi.fn();
const toastError = vi.fn();

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: (...args: unknown[]) => fetchWithTimeout(...args),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
  },
}));

vi.mock('@/lib/utils/localeUtils', () => ({
  getClientLocale: () => 'en',
}));

function buildCtx(data: StreamCtx['data']): { ctx: StreamCtx; setLoading: ReturnType<typeof vi.fn> } {
  const setLoading = vi.fn();
  const state: StreamHandlerState = {
    messages: [],
    agentConfig: { browserSource: 'auto' },
  } as StreamHandlerState;
  const actions = {
    setMessages: vi.fn(),
    setLoading,
  } as unknown as StreamHandlerActions;

  return {
    ctx: {
      data,
      added: {},
      state,
      actions,
      recievedMessage: null,
    },
    setLoading,
  };
}

describe('fileDiffEvents browser takeover', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useBrowserTakeoverStore.getState().completeTakeover();
    fetchWithTimeout.mockResolvedValue({ ok: true });
  });

  it('skips VNC POST when harness reports is_managed=false', async () => {
    const { ctx, setLoading } = buildCtx({
      type: AgentEventType.BROWSER_TAKEOVER_REQUESTED,
      messageId: 'msg-42',
      data: {
        reason: 'Enter SMS code',
        is_managed: false,
        url: 'https://bank.example/login',
      },
    });

    await fileDiffEvents(ctx);

    expect(fetchWithTimeout).not.toHaveBeenCalled();
    expect(useBrowserTakeoverStore.getState().pending).toBe(true);
    expect(useBrowserTakeoverStore.getState().uiMode).toBe('extension');
    expect(setLoading).toHaveBeenCalledWith(false);
  });

  it('calls VNC POST when harness reports is_managed=true', async () => {
    const { ctx } = buildCtx({
      type: AgentEventType.BROWSER_TAKEOVER_REQUESTED,
      messageId: 'msg-43',
      data: {
        reason: 'Complete payment in sandbox browser',
        is_managed: true,
      },
    });

    await fileDiffEvents(ctx);

    expect(fetchWithTimeout).toHaveBeenCalledWith('/webui/vnc/takeover', expect.objectContaining({ method: 'POST' }));
    expect(useBrowserTakeoverStore.getState().uiMode).toBe('managed');
  });

  it('shows toast when managed VNC POST returns non-ok', async () => {
    fetchWithTimeout.mockResolvedValue({ ok: false, status: 503 });
    const { ctx } = buildCtx({
      type: AgentEventType.BROWSER_TAKEOVER_REQUESTED,
      messageId: 'msg-44',
      data: {
        reason: 'Complete payment in sandbox browser',
        is_managed: true,
      },
    });

    await fileDiffEvents(ctx);

    await vi.waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(
        expect.stringContaining('visual desktop'),
        expect.objectContaining({ duration: 8000 }),
      );
    });
    expect(useBrowserTakeoverStore.getState().pending).toBe(true);
  });
});
