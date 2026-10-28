import { describe, expect, it } from 'vitest';

import type { Message } from '@/store/chat/types';
import { parseMessages } from '@/store/chat/messageHydration';

function persistedUserRow(metadata: Record<string, unknown> | string | null): Message {
  return {
    messageId: 'wakeup_followup_t1',
    chatId: 'chat-1',
    role: 'user',
    content: '<system_notification type="adaptive_wakeup_followup">done</system_notification>',
    createdAt: new Date('2026-10-13T00:00:00.000Z'),
    metadata,
  } as unknown as Message;
}

describe('parseMessages wake notice marker', () => {
  it.each(['followup', 'degraded', 'suppressed'] as const)('reads the `%s` kind the server persisted', (kind) => {
    const [parsed] = parseMessages([persistedUserRow({ wakeup_notice: kind })]);

    expect(parsed.wakeupNotice).toBe(kind);
  });

  it('reads the kind from metadata persisted as a JSON string', () => {
    const [parsed] = parseMessages([persistedUserRow(JSON.stringify({ wakeup_notice: 'degraded' }))]);

    expect(parsed.wakeupNotice).toBe('degraded');
  });

  it.each([
    ['a row without metadata', null],
    ['a kind the client does not know', { wakeup_notice: 'unknown' }],
    ['a marker that is a boolean', { wakeup_notice: true }],
    ['a message the user typed', { spillover: undefined }],
  ])('does not mark %s', (_label, metadata) => {
    const [parsed] = parseMessages([persistedUserRow(metadata)]);

    expect(parsed.wakeupNotice).toBeUndefined();
  });
});
