import { describe, expect, it } from 'vitest';

import type { Message } from '@/store/chat/types';
import { parseMessages } from '@/store/chat/messageHydration';

function persisted(metadata: Record<string, unknown> | string | null): Message {
  return {
    messageId: 'm-1',
    chatId: 'chat-1',
    role: 'assistant',
    content: 'done',
    createdAt: new Date('2026-10-13T00:00:00.000Z'),
    metadata,
  } as unknown as Message;
}

describe('parseMessages system notice marker', () => {
  it.each(['background_job', 'voice_background_task'])(
    'marks a persisted row carrying `%s: true` as a notice',
    (key) => {
      const [parsed] = parseMessages([persisted({ [key]: true, status: 'completed' })]);

      expect(parsed.isSystemNotice).toBe(true);
    },
  );

  it('reads the marker from metadata persisted as a JSON string', () => {
    const [parsed] = parseMessages([persisted(JSON.stringify({ background_job: true }))]);

    expect(parsed.isSystemNotice).toBe(true);
  });

  it.each([
    ['an ordinary answer', { routingTier: 'simple' }],
    ['a row without metadata', null],
    ['a marker that is not true', { background_job: false }],
    ['a marker that is a string', { background_job: 'true' }],
  ])('does not mark %s', (_label, metadata) => {
    const [parsed] = parseMessages([persisted(metadata)]);

    expect(parsed.isSystemNotice).toBeUndefined();
  });
});
