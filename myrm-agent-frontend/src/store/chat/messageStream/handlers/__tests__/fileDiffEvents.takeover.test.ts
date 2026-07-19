import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType } from '@/store/chat/types';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import type { StreamCtx } from '../../streamContext';
import { fileDiffEvents } from '../fileDiffEvents';

const fetchWithTimeout = vi.fn();

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: (...args: unknown[]) => fetchWithTimeout(...args),
}));

function buildCtx(data: StreamCtx['data']): StreamCtx {
  const state: StreamHandlerState = {
    messages: [],
    agentConfig: { browserSource: 'auto' },
  } as StreamHandlerState;
  const actions = {
    setMessages: vi.fn(),
  } as unknown as StreamHandlerActions;

  return {
    data,
    added: {},
    state,
    actions,
    recievedMessage: null,
  };
}

describe('fileDiffEvents browser takeover', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useBrowserTakeoverStore.getState().completeTakeover();
    fetchWithTimeout.mockResolvedValue({ ok: true });
  });

  it('skips VNC POST when harness reports is_managed=false', async () => {
    const ctx = buildCtx({
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
  });

  it('calls VNC POST when harness reports is_managed=true', async () => {
    const ctx = buildCtx({
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
});
