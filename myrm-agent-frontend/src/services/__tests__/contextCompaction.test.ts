import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '@/lib/api';
import { COMPACT_FOCUS_TOPIC_MAX_LENGTH } from '@/lib/constants/compact-focus-topic';
import { compactChat } from '@/services/contextCompaction';

vi.mock('@/lib/api', () => ({
  API_BASE_URL: '',
  apiRequest: vi.fn(),
  fetchWithTimeout: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);
const RARE_HAN = String.fromCodePoint(0x20bb7);

/** The focus topic the request carried, or undefined when it carried no body. */
function sentTopic(): string | undefined {
  const [, init] = apiRequestMock.mock.calls[0];
  return init?.body === undefined ? undefined : (JSON.parse(String(init.body)) as { focus_topic: string }).focus_topic;
}

describe('compactChat', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    apiRequestMock.mockResolvedValue({ compacted: true, message_count: 4, tokens_saved: 900, reason: null });
  });

  it('sends a topic within the limit as it is', async () => {
    await compactChat('chat-1', 'billing decisions');

    expect(apiRequestMock).toHaveBeenCalledWith('/chats/chat-1/compact', {
      method: 'POST',
      body: JSON.stringify({ focus_topic: 'billing decisions' }),
      headers: { 'Content-Type': 'application/json' },
    });
  });

  it.each([undefined, ''])('sends no body when the topic is %j', async (topic) => {
    await compactChat('chat-1', topic);

    expect(apiRequestMock).toHaveBeenCalledWith('/chats/chat-1/compact', { method: 'POST' });
  });

  it('cuts a longer topic to the limit the server accepts, so the request is not refused', async () => {
    await compactChat('chat-1', 'x'.repeat(COMPACT_FOCUS_TOPIC_MAX_LENGTH + 60));

    expect(sentTopic()).toBe('x'.repeat(COMPACT_FOCUS_TOPIC_MAX_LENGTH));
  });

  it('cuts by character, so a rare han character on the limit is not split in half', async () => {
    await compactChat('chat-1', `a${RARE_HAN.repeat(COMPACT_FOCUS_TOPIC_MAX_LENGTH + 10)}`);

    expect(sentTopic()).toBe(`a${RARE_HAN.repeat(COMPACT_FOCUS_TOPIC_MAX_LENGTH - 1)}`);
  });
});
