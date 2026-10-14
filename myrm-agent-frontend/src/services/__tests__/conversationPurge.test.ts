import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest } from '@/lib/api';
import { ConversationPurgeBusyError, purgeAllConversations } from '@/services/conversationPurge';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('purgeAllConversations', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('posts to the safe purge with a timeout that outlasts a large vault and reports failures to its caller', async () => {
    apiRequestMock.mockResolvedValue({ status: 'success', purged_chats: 7 });

    const result = await purgeAllConversations();

    expect(result.purged_chats).toBe(7);
    // The card tells the user itself; a request-level toast would report the same failure twice.
    expect(apiRequestMock).toHaveBeenCalledWith('/health/database/safe-purge', {
      method: 'POST',
      silent: true,
      timeout: 300_000,
    });
  });

  it('turns the server refusal for a running conversation into a typed error', async () => {
    apiRequestMock.mockRejectedValue(new ApiError('busy', 409));

    await expect(purgeAllConversations()).rejects.toBeInstanceOf(ConversationPurgeBusyError);
  });

  it('lets every other failure through untouched', async () => {
    const failure = new ApiError('boom', 500);
    apiRequestMock.mockRejectedValue(failure);

    await expect(purgeAllConversations()).rejects.toBe(failure);
  });
});
