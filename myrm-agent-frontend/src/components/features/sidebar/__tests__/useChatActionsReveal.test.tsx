import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { revealChatArtifacts } from '@/services/file';
import { toast } from '@/hooks/shared/useToast';
import { useChatActions } from '@/components/features/sidebar/useChatActions';

vi.mock('@/services/chat', () => ({
  updateChatTitle: vi.fn(),
  deleteChat: vi.fn(),
  exportChat: vi.fn(),
  createChatShare: vi.fn(),
  revokeChatShare: vi.fn(),
  getChatShareStatus: vi.fn(),
}));

vi.mock('@/services/file', () => ({
  revealChatArtifacts: vi.fn(),
}));

vi.mock('@/store/useChatStore', () => {
  const storeFn: any = () => ({ pinChat: vi.fn(), unpinChat: vi.fn() });
  storeFn.getState = () => ({ setChatHistoryItems: vi.fn() });
  return {
    default: storeFn,
    __esModule: true,
  };
});

vi.mock('@/hooks/shared/useToast', () => ({
  toast: vi.fn(),
}));

const t = ((key: string) => key) as ReturnType<typeof import('next-intl').useTranslations>;

describe('useChatActions handleRevealArtifacts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('triggers revealChatArtifacts and toasts success on ok status', async () => {
    vi.mocked(revealChatArtifacts).mockResolvedValue({
      status: 'ok',
      path: '/workspace/sandboxes/chat-1',
      artifact_count: 2,
    });

    const { result } = renderHook(() => useChatActions([], t));

    await act(async () => {
      await result.current.handleRevealArtifacts('chat-1');
    });

    expect(revealChatArtifacts).toHaveBeenCalledWith('chat-1');
    expect(toast).toHaveBeenCalledWith({
      title: 'chat.revealArtifacts.success',
      variant: 'default',
    });
    expect(result.current.revealingArtifactsChatId).toBeNull();
  });

  it('toasts noArtifacts when no artifacts found', async () => {
    vi.mocked(revealChatArtifacts).mockResolvedValue({
      status: 'no_artifacts',
      path: null,
      artifact_count: 0,
    });

    const { result } = renderHook(() => useChatActions([], t));

    await act(async () => {
      await result.current.handleRevealArtifacts('chat-empty');
    });

    expect(revealChatArtifacts).toHaveBeenCalledWith('chat-empty');
    expect(toast).toHaveBeenCalledWith({
      title: 'chat.revealArtifacts.noArtifacts',
      variant: 'default',
    });
    expect(result.current.revealingArtifactsChatId).toBeNull();
  });

  it('toasts missingOnDisk when files are gone from disk', async () => {
    vi.mocked(revealChatArtifacts).mockResolvedValue({
      status: 'missing_on_disk',
      path: null,
      artifact_count: 1,
    });

    const { result } = renderHook(() => useChatActions([], t));

    await act(async () => {
      await result.current.handleRevealArtifacts('chat-missing');
    });

    expect(revealChatArtifacts).toHaveBeenCalledWith('chat-missing');
    expect(toast).toHaveBeenCalledWith({
      title: 'chat.revealArtifacts.missingOnDisk',
      variant: 'destructive',
    });
  });

  it('handles network or server error gracefully', async () => {
    vi.mocked(revealChatArtifacts).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useChatActions([], t));

    await act(async () => {
      await result.current.handleRevealArtifacts('chat-err');
    });

    expect(toast).toHaveBeenCalledWith({
      title: 'chat.revealArtifacts.error',
      description: 'Network error',
      variant: 'destructive',
    });
    expect(result.current.revealingArtifactsChatId).toBeNull();
  });
});
