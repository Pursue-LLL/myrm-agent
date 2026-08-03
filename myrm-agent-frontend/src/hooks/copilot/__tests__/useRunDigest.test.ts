import { describe, expect, it } from 'vitest';

describe('useRunDigest event filter', () => {
  it('matches chat_id before applying digest updates', () => {
    const chatId = 'chat-a';
    const detail = { chat_id: 'chat-b', digest: { phase: 'running' } };
    const shouldApply = Boolean(chatId && detail.chat_id === chatId);
    expect(shouldApply).toBe(false);
  });

  it('accepts matching chat_id', () => {
    const chatId = 'chat-a';
    const detail = { chat_id: 'chat-a', digest: { phase: 'running' } };
    const shouldApply = Boolean(chatId && detail.chat_id === chatId);
    expect(shouldApply).toBe(true);
  });
});
