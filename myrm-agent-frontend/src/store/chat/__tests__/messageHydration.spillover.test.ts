import { describe, expect, it } from 'vitest';

import type { Message } from '@/store/chat/types';
import { parseMessages } from '@/store/chat/messageHydration';

function persisted(metadata: Record<string, unknown>): Message {
  return {
    messageId: 'm-1',
    chatId: 'chat-1',
    role: 'user',
    content: '<file_spillover path="/work/.myrm/pastes/payload_1.md"></file_spillover>',
    createdAt: new Date('2026-10-27T00:00:00.000Z'),
    metadata,
  } as unknown as Message;
}

describe('parseMessages parked pasted text', () => {
  it('turns the server metadata into the typed spillover of the message', () => {
    const [parsed] = parseMessages([
      persisted({
        spillover: {
          spillover_path: '/work/.myrm/pastes/payload_1.md',
          original_char_count: 48_000,
          sha256: 'abc',
          preview: 'Q3 review',
        },
      }),
    ]);

    expect(parsed.spillover).toEqual({ path: '/work/.myrm/pastes/payload_1.md', chars: 48_000, preview: 'Q3 review' });
  });

  it('does not let metadata that points at no file through as a spillover', () => {
    const [parsed] = parseMessages([persisted({ spillover: { sha256: 'abc' } })]);

    expect(parsed.spillover).toBeUndefined();
  });

  it('leaves an ordinary message without a spillover', () => {
    const [parsed] = parseMessages([persisted({})]);

    expect(parsed.spillover).toBeUndefined();
  });
});
