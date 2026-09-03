/**
 * Unit tests for useChatActions artifact reveal action.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useChatActions } from '../useChatActions';
import * as fileService from '@/services/file';
import { toast } from '@/hooks/shared/useToast';

vi.mock('@/hooks/shared/useToast', () => ({
  toast: vi.fn(),
}));

vi.mock('@/services/chat', () => ({
  updateChatTitle: vi.fn(),
  deleteChat: vi.fn(),
  exportChat: vi.fn(),
  createChatShare: vi.fn(),
  revokeChatShare: vi.fn(),
  getChatShareStatus: vi.fn().mockResolvedValue({ shared: false }),
}));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(() => ({ pinChat: vi.fn(), unpinChat: vi.fn() }), {
    getState: () => ({ setChatHistoryItems: vi.fn() }),
  }),
  __esModule: true,
}));

const mockT = ((key: string) => {
  const dict: Record<string, string> = {
    'chat.revealArtifacts.success': 'Opened artifacts folder',
    'chat.revealArtifacts.noArtifacts': 'No artifacts found',
    'chat.revealArtifacts.missingOnDisk': 'Files missing on disk',
    'chat.revealArtifacts.error': 'Failed to open folder',
  };
  return dict[key] || key;
}) as any;

describe('useChatActions handleRevealArtifacts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('triggers success toast when status is ok', async () => {
    const revealSpy = vi.spyOn(fileService, 'revealChatArtifacts').mockResolvedValue({
      status: 'ok',
      path: '/workspace/sandboxes/chat-1',
      artifact_count: 2,
    });

    const { result } = renderHook(() => useChatActions([], mockT));

    await act(async () => {
      await result.current.handleRevealArtifacts('chat-1');
    });

    expect(revealSpy).toHaveBeenCalledWith('chat-1');
    expect(toast).toHaveBeenCalledWith({
      title: 'Opened artifacts folder',
      variant: 'default',
    });
    expect(result.current.revealingArtifactsChatId).toBeNull();
  });

  it('triggers info toast when status is no_artifacts', async () => {
    vi.spyOn(fileService, 'revealChatArtifacts').mockResolvedValue({
      status: 'no_artifacts',
      path: null,
      artifact_count: 0,
    });

    const { result } = renderHook(() => useChatActions([], mockT));

    await act(async () => {
      await result.current.handleRevealArtifacts('chat-empty');
    });

    expect(toast).toHaveBeenCalledWith({
      title: 'No artifacts found',
      variant: 'default',
    });
  });

  it('triggers destructive toast when status is missing_on_disk', async () => {
    vi.spyOn(fileService, 'revealChatArtifacts').mockResolvedValue({
      status: 'missing_on_disk',
      path: null,
      artifact_count: 1,
    });

    const { result } = renderHook(() => useChatActions([], mockT));

    await act(async () => {
      await result.current.handleRevealArtifacts('chat-missing');
    });

    expect(toast).toHaveBeenCalledWith({
      title: 'Files missing on disk',
      variant: 'destructive',
    });
  });

  it('triggers destructive toast on API failure', async () => {
    vi.spyOn(fileService, 'revealChatArtifacts').mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useChatActions([], mockT));

    await act(async () => {
      await result.current.handleRevealArtifacts('chat-fail');
    });

    expect(toast).toHaveBeenCalledWith({
      title: 'Failed to open folder',
      description: 'Network error',
      variant: 'destructive',
    });
    expect(result.current.revealingArtifactsChatId).toBeNull();
  });
});
