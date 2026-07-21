import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType } from '@/store/chat/types';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useChatStore from '@/store/useChatStore';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import type { StreamCtx } from '../../streamContext';
import { fileDiffEvents } from '../fileDiffEvents';

const fetchWithTimeout = vi.fn();
const toastError = vi.fn();
const createPairingToken = vi.fn();

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

vi.mock('@/services/remoteAccess', () => ({
  remoteAccessService: {
    createPairingToken: (...args: unknown[]) => createPairingToken(...args),
  },
}));

function buildCtx(data: StreamCtx['data']): { ctx: StreamCtx; setLoading: ReturnType<typeof vi.fn> } {
  const setLoading = vi.fn();
  const state: StreamHandlerState = {
    messages: [],
    messageAppeared: false,
    loading: false,
    scheduler: {} as StreamHandlerState['scheduler'],
  };
  const actions: StreamHandlerActions = {
    setMessages: vi.fn(),
    setMessageAppeared: vi.fn(),
    setLoading,
    _processSuggestions: vi.fn(async () => undefined),
    scheduleAutoSave: vi.fn(),
  };

  return {
    ctx: {
      data,
      input: '',
      sources: undefined,
      added: false,
      state,
      actions,
      recievedMessage: '',
      files: [],
    },
    setLoading,
  };
}

describe('fileDiffEvents browser takeover', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useBrowserTakeoverStore.getState().completeTakeover();
    useChatStore.setState({ chatId: undefined });
    fetchWithTimeout.mockResolvedValue({ ok: true });
    createPairingToken.mockResolvedValue({
      token: 'pair-token',
      mobilePath: '/mobile/takeover/chat-42?pair=pair-token',
    });
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

  it('creates signed takeover live link for extension takeover', async () => {
    useChatStore.setState({ chatId: 'chat-42' });
    const { ctx } = buildCtx({
      type: AgentEventType.BROWSER_TAKEOVER_REQUESTED,
      messageId: 'msg-45',
      data: {
        reason: 'Enter MFA code',
        is_managed: false,
        url: 'https://example.com/login',
      },
    });

    await fileDiffEvents(ctx);

    await vi.waitFor(() => {
      expect(createPairingToken).toHaveBeenCalledWith('chat-42', 'browser_takeover');
      expect(useBrowserTakeoverStore.getState().liveAssistUrl).toContain('/mobile/takeover/chat-42?pair=pair-token');
    });
    expect(useBrowserTakeoverStore.getState().liveAssistUrl).toContain('mid=msg-45');
  });

  it('uses backend-provided takeover live link without issuing fallback token', async () => {
    const backendLink = 'https://remote.example/mobile/takeover/chat-42?pair=server-token&mid=msg-46';
    const { ctx } = buildCtx({
      type: AgentEventType.BROWSER_TAKEOVER_REQUESTED,
      messageId: 'msg-46',
      data: {
        reason: 'Confirm login',
        is_managed: false,
        url: 'https://example.com/confirm',
        live_assist_url: backendLink,
      },
    });

    await fileDiffEvents(ctx);

    expect(createPairingToken).not.toHaveBeenCalled();
    expect(useBrowserTakeoverStore.getState().liveAssistUrl).toBe(backendLink);
  });
});
