import { renderHook, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { createChatShare, getChatShareStatus, revokeChatShare } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { useChatActions } from '@/components/features/sidebar/useChatActions';

vi.mock('@/services/chat', () => ({
  updateChatTitle: vi.fn(),
  deleteChat: vi.fn(),
  exportChat: vi.fn(),
  createChatShare: vi.fn(),
  revokeChatShare: vi.fn(),
  getChatShareStatus: vi.fn(),
}));

vi.mock('@/store/useChatStore', () => ({
  default: () => ({ pinChat: vi.fn(), unpinChat: vi.fn() }),
  __esModule: true,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: vi.fn(),
}));

const t = ((key: string) => key) as ReturnType<typeof import('next-intl').useTranslations>;

describe('useChatActions share lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('opens the dialog and reflects an active unprotected share', async () => {
    vi.mocked(getChatShareStatus).mockResolvedValue({
      shared: true,
      revoked: false,
      password_protected: false,
      share_url: 'https://example.com/s/abc',
      expires_at: 1700000000,
    });

    const { result } = renderHook(() => useChatActions([], t));

    await act(async () => {
      await result.current.handleShare('chat-1');
    });

    expect(result.current.shareDialogOpen).toBe(true);
    expect(result.current.shareChatId).toBe('chat-1');
    expect(result.current.shareUrl).toBe('https://example.com/s/abc');
    expect(result.current.shareExpiresAt).toBe(1700000000);
    expect(result.current.shareRevoked).toBe(false);
    expect(result.current.sharePasswordProtected).toBe(false);
    expect(result.current.shareLoading).toBe(false);
  });

  it('reflects a revoked share', async () => {
    vi.mocked(getChatShareStatus).mockResolvedValue({
      shared: true,
      revoked: true,
      password_protected: false,
      share_url: null,
      expires_at: null,
    });

    const { result } = renderHook(() => useChatActions([], t));

    await act(async () => {
      await result.current.handleShare('chat-1');
    });

    expect(result.current.shareRevoked).toBe(true);
    expect(result.current.shareUrl).toBeNull();
  });

  it('stays usable when the status query fails', async () => {
    vi.mocked(getChatShareStatus).mockRejectedValue(new Error('network'));

    const { result } = renderHook(() => useChatActions([], t));

    await act(async () => {
      await result.current.handleShare('chat-1');
    });

    expect(result.current.shareDialogOpen).toBe(true);
    expect(result.current.shareLoading).toBe(false);
    expect(result.current.shareUrl).toBeNull();
  });

  it('creates a share and stores the returned link', async () => {
    vi.mocked(getChatShareStatus).mockResolvedValue({
      shared: false,
      revoked: false,
      password_protected: false,
      share_url: null,
      expires_at: null,
    });
    vi.mocked(createChatShare).mockResolvedValue({
      token: 'tok-1',
      chat_id: 'chat-1',
      share_url: 'https://example.com/s/new',
      expires_at: 1700000100,
      password_protected: false,
    });

    const { result } = renderHook(() => useChatActions([], t));

    await act(async () => {
      await result.current.handleShare('chat-1');
    });
    // State updates are flushed; handleShareCreate now closes over chat-1.
    await act(async () => {
      await result.current.handleShareCreate(7);
    });

    expect(createChatShare).toHaveBeenCalledWith('chat-1', 7, undefined);
    expect(result.current.shareUrl).toBe('https://example.com/s/new');
    expect(result.current.shareExpiresAt).toBe(1700000100);
    expect(result.current.shareRevoked).toBe(false);
    expect(result.current.shareLoading).toBe(false);
  });

  it('revokes a share and clears the link state', async () => {
    vi.mocked(getChatShareStatus).mockResolvedValue({
      shared: true,
      revoked: false,
      password_protected: false,
      share_url: 'https://example.com/s/abc',
      expires_at: 1700000000,
    });
    vi.mocked(revokeChatShare).mockResolvedValue(undefined);

    const { result } = renderHook(() => useChatActions([], t));

    await act(async () => {
      await result.current.handleShare('chat-1');
    });
    // State updates are flushed; handleShareRevoke now closes over chat-1.
    await act(async () => {
      await result.current.handleShareRevoke();
    });

    expect(revokeChatShare).toHaveBeenCalledWith('chat-1');
    expect(result.current.shareUrl).toBeNull();
    expect(result.current.shareExpiresAt).toBeNull();
    expect(result.current.shareRevoked).toBe(true);
  });

  it('keeps the dialog open when revoke fails', async () => {
    vi.mocked(getChatShareStatus).mockResolvedValue({
      shared: true,
      revoked: false,
      password_protected: false,
      share_url: 'https://example.com/s/abc',
      expires_at: 1700000000,
    });
    vi.mocked(revokeChatShare).mockRejectedValue(new Error('boom'));

    const { result } = renderHook(() => useChatActions([], t));

    await act(async () => {
      await result.current.handleShare('chat-1');
    });
    // State updates are flushed; handleShareRevoke now closes over chat-1.
    await act(async () => {
      await result.current.handleShareRevoke();
    });

    expect(revokeChatShare).toHaveBeenCalledWith('chat-1');
    expect(result.current.shareRevoked).toBe(false);
  });
});
