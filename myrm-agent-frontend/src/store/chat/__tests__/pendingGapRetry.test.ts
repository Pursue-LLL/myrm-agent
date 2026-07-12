import { beforeEach, describe, expect, it, vi } from 'vitest';

const sendMessage = vi.fn().mockResolvedValue(undefined);
const clearPendingGapRetry = vi.fn();
let mockState = {
  pendingGapRetry: null as
    | { kind: 'capability'; text: string; toolId: string }
    | { kind: 'skill'; text: string; skillId: string }
    | null,
  loading: false,
  currentBuiltinTools: ['web_search', 'memory'],
  agentConfig: { selectedSkillIds: ['bound_skill'] as string[] },
  sendMessage,
  clearPendingGapRetry,
};

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => mockState,
  },
}));

import {
  flushPendingGapRetry,
  resolveLastPlainUserMessage,
  scheduleFlushPendingGapRetry,
} from '../pendingGapRetry';
import type { Message } from '@/store/chat/types';

describe('pendingGapRetry', () => {
  beforeEach(() => {
    sendMessage.mockClear();
    clearPendingGapRetry.mockClear();
    mockState = {
      pendingGapRetry: null,
      loading: false,
      currentBuiltinTools: ['web_search', 'memory'],
      agentConfig: { selectedSkillIds: ['bound_skill'] },
      sendMessage,
      clearPendingGapRetry,
    };
  });

  it('resolveLastPlainUserMessage returns the latest plain user text', () => {
    const messages: Message[] = [
      { role: 'user', content: 'first', messageId: '1', chatId: 'c1', createdAt: new Date() },
      { role: 'assistant', content: 'ok', messageId: '2', chatId: 'c1', createdAt: new Date() },
      { role: 'user', content: '  second request  ', messageId: '3', chatId: 'c1', createdAt: new Date() },
    ];
    expect(resolveLastPlainUserMessage(messages)).toBe('second request');
  });

  it('flushPendingGapRetry sends deferred capability message when tool is enabled', async () => {
    mockState.pendingGapRetry = {
      kind: 'capability',
      text: 'deploy staging form',
      toolId: 'render_ui',
    };
    mockState.currentBuiltinTools = ['web_search', 'memory', 'render_ui'];

    const flushed = await flushPendingGapRetry();

    expect(flushed).toBe(true);
    expect(sendMessage).toHaveBeenCalledWith('deploy staging form', expect.any(String));
    expect(clearPendingGapRetry).toHaveBeenCalledTimes(1);
  });

  it('flushPendingGapRetry skips while stream is loading', async () => {
    mockState.pendingGapRetry = {
      kind: 'capability',
      text: 'deploy staging form',
      toolId: 'render_ui',
    };
    mockState.loading = true;
    mockState.currentBuiltinTools = ['web_search', 'memory', 'render_ui'];

    const flushed = await flushPendingGapRetry();

    expect(flushed).toBe(false);
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it('flushPendingGapRetry skips when entitlement is still missing', async () => {
    mockState.pendingGapRetry = {
      kind: 'skill',
      text: 'run github flow',
      skillId: 'github_pr_skill',
    };

    const flushed = await flushPendingGapRetry();

    expect(flushed).toBe(false);
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it('scheduleFlushPendingGapRetry delegates to flush after microtask', async () => {
    mockState.pendingGapRetry = {
      kind: 'capability',
      text: 'deploy staging form',
      toolId: 'render_ui',
    };
    mockState.currentBuiltinTools = ['web_search', 'memory', 'render_ui'];

    scheduleFlushPendingGapRetry();
    await Promise.resolve();

    expect(sendMessage).toHaveBeenCalledWith('deploy staging form', expect.any(String));
  });
});
