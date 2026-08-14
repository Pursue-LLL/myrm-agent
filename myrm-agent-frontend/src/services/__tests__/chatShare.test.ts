import { describe, expect, it, vi, beforeEach } from 'vitest';
import { apiRequest } from '@/lib/api';
import { getChatShareStatus, createChatShare, revokeChatShare } from '@/services/chat';

vi.mock('@/lib/api', () => ({
  API_BASE_URL: '',
  apiRequest: vi.fn(),
  fetchWithTimeout: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('chat share services', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('getChatShareStatus queries the share status endpoint (GET)', async () => {
    const payload = {
      shared: true,
      revoked: false,
      password_protected: false,
      share_url: 'https://share.example.com/chat-1/abc',
      expires_at: 1_800_000_000,
    };
    apiRequestMock.mockResolvedValue(payload);

    const status = await getChatShareStatus('chat-1');

    expect(apiRequestMock).toHaveBeenCalledWith('/chats/chat-1/share');
    expect(status).toEqual(payload);
  });

  it('createChatShare posts ttl_days and omits password when absent', async () => {
    apiRequestMock.mockResolvedValue({
      token: 'abc',
      share_url: 'https://share.example.com/chat-1/abc',
      expires_at: 1_800_000_000,
      chat_id: 'chat-1',
      password_protected: false,
    });

    const result = await createChatShare('chat-1', 14);

    expect(apiRequestMock).toHaveBeenCalledWith(
      '/chats/chat-1/share',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ ttl_days: 14 }),
      }),
    );
    expect(result.share_url).toContain('chat-1');
  });

  it('createChatShare includes password when provided', async () => {
    apiRequestMock.mockResolvedValue({
      token: 'abc',
      share_url: 'https://share.example.com/chat-1/abc',
      expires_at: 1_800_000_000,
      chat_id: 'chat-1',
      password_protected: true,
    });

    await createChatShare('chat-1', 7, 'secret');

    expect(apiRequestMock).toHaveBeenCalledWith(
      '/chats/chat-1/share',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ ttl_days: 7, password: 'secret' }),
      }),
    );
  });

  it('revokeChatShare issues a DELETE', async () => {
    apiRequestMock.mockResolvedValue(undefined);

    await revokeChatShare('chat-1');

    expect(apiRequestMock).toHaveBeenCalledWith('/chats/chat-1/share', {
      method: 'DELETE',
    });
  });
});
