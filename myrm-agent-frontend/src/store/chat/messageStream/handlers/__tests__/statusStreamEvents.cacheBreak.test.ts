/**
 * cache_break SSE status — the optional "cache reset" notice.
 *
 * The notice is translated copy (not a literal), and only appears when the user enabled cache-break
 * notifications; the uncached-token clause is driven by the `tokens` value the handler passes.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const configState = vi.hoisted(() => ({ enableCacheBreakNotification: true }));

vi.mock('../handlerDeps', () => ({
  AgentEventType: { STATUS: 'status' },
  findAssistantMessageIndex: vi.fn(() => 0),
  useConfigStore: { getState: () => configState },
}));

vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: vi.fn(),
}));

import { showI18nToast } from '@/services/i18nToastService';
import { statusStreamEvents } from '../statusStreamEvents';
import type { StreamCtx } from '../../streamContext';

function makeCacheBreakCtx(data: Record<string, unknown>): StreamCtx {
  const state = { messages: [{ messageId: 'msg-1', role: 'assistant' } as Record<string, unknown>] };
  return {
    data: { type: 'status', step_key: 'cache_break', messageId: 'msg-1', data } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: {} as never,
    actions: {
      setLoading: vi.fn(),
      setMessages: vi.fn((updater: (s: typeof state) => void) => updater(state)),
    } as never,
    files: [],
  };
}

describe('statusStreamEvents cache_break notice', () => {
  beforeEach(() => {
    configState.enableCacheBreakNotification = true;
    vi.mocked(showI18nToast).mockClear();
  });

  it('passes the reason and the rounded uncached thousands of tokens to the translated notice', async () => {
    await statusStreamEvents(makeCacheBreakCtx({ reason: 'system prompt changed', token_drop: 5400 }));

    await vi.waitFor(() => expect(showI18nToast).toHaveBeenCalledTimes(1));
    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.cacheResetNotice',
      { reason: 'system prompt changed', tokens: 5 },
      { type: 'info', duration: 5000 },
    );
  });

  it('omits the token clause when 1000 tokens or fewer were uncached', async () => {
    await statusStreamEvents(makeCacheBreakCtx({ reason: 'tools changed', token_drop: 1000 }));

    await vi.waitFor(() => expect(showI18nToast).toHaveBeenCalledTimes(1));
    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.cacheResetNotice',
      { reason: 'tools changed', tokens: 0 },
      { type: 'info', duration: 5000 },
    );
  });

  it('shows nothing when the user turned cache-break notifications off', async () => {
    configState.enableCacheBreakNotification = false;

    await statusStreamEvents(makeCacheBreakCtx({ reason: 'tools changed', token_drop: 5400 }));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(showI18nToast).not.toHaveBeenCalled();
  });

  it('shows nothing without a reason', async () => {
    await statusStreamEvents(makeCacheBreakCtx({ token_drop: 5400 }));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(showI18nToast).not.toHaveBeenCalled();
  });
});
