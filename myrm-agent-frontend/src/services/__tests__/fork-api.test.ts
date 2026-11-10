import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api';
import { forkConversation, getForkInfo } from '@/services/fork-api';

beforeEach(() => {
  vi.mocked(apiRequest).mockReset();
  vi.mocked(apiRequest).mockResolvedValue({ success: true, data: {} });
});

describe('getForkInfo', () => {
  it('reads the fork info of the chat without raising an error toast of its own', async () => {
    await getForkInfo('chat-1');

    expect(apiRequest).toHaveBeenCalledExactlyOnceWith('/chats/chat-1/fork-info', { silent: true });
  });
});

describe('forkConversation', () => {
  it('posts the message index and a plain fork by default', async () => {
    await forkConversation('chat-1', 3);

    const [url, options] = vi.mocked(apiRequest).mock.calls[0];
    expect(url).toBe('/chats/chat-1/fork');
    expect(options).toMatchObject({ method: 'POST' });
    expect(JSON.parse(String((options as RequestInit).body))).toEqual({ message_index: 3, fork_mode: 'full_clone' });
  });

  it('carries the title, the acceptance mode and its scope when given', async () => {
    await forkConversation('chat-1', 0, 'Retry', 'acceptance_verifier', 'only the api');

    expect(JSON.parse(String((vi.mocked(apiRequest).mock.calls[0][1] as RequestInit).body))).toEqual({
      message_index: 0,
      new_title: 'Retry',
      fork_mode: 'acceptance_verifier',
      acceptance_scope: 'only the api',
    });
  });
});
