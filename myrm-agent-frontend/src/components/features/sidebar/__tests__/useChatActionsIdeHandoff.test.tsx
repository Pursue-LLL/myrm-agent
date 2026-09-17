/**
 * Unit tests for useChatActions external IDE handoff action.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useChatActions } from '../useChatActions';
import { exportChat } from '@/services/chat';
import { copyAsMarkdown } from '@/lib/utils/chatExport';
import { desktopBridge } from '@/lib/desktopBridge';
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

vi.mock('@/lib/utils/chatExport', () => ({
  copyAsMarkdown: vi.fn(),
  downloadAsHtml: vi.fn(),
  downloadAsJson: vi.fn(),
  downloadAsMarkdown: vi.fn(),
  printChat: vi.fn(),
}));

vi.mock('@/lib/desktopBridge', () => ({
  desktopBridge: { openExternal: vi.fn() },
}));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(() => ({ pinChat: vi.fn(), unpinChat: vi.fn() }), {
    getState: () => ({ setChatHistoryItems: vi.fn() }),
  }),
  __esModule: true,
}));

const mockT = ((key: string) => {
  const dict: Record<string, string> = {
    'chat.exportChat.noMessages': 'No messages to handoff',
    'chat.ideHandoff.copiedReady': 'Handoff copied — paste it in your IDE',
    'chat.ideHandoff.failed': 'Failed to prepare IDE handoff',
  };
  return dict[key] || key;
}) as any;

const nonEmptyExport = { messages: [{ id: 'm1' }], redacted: true };

describe('useChatActions handleOpenInIDE', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('copies the bundle, launches the IDE and toasts readiness', async () => {
    vi.mocked(exportChat).mockResolvedValue(nonEmptyExport as any);
    const { result } = renderHook(() => useChatActions([], mockT));

    await act(async () => {
      await result.current.handleOpenInIDE('chat-1', 'cursor');
    });

    expect(exportChat).toHaveBeenCalledWith('chat-1');
    expect(copyAsMarkdown).toHaveBeenCalledWith(nonEmptyExport);
    expect(desktopBridge.openExternal).toHaveBeenCalledWith('cursor://');
    expect(toast).toHaveBeenCalledWith({
      title: 'Handoff copied — paste it in your IDE',
      variant: 'default',
    });
    expect(result.current.exportingId).toBeNull();
  });

  it('warns on empty chats without launching', async () => {
    vi.mocked(exportChat).mockResolvedValue({ messages: [], redacted: false } as any);
    const { result } = renderHook(() => useChatActions([], mockT));

    await act(async () => {
      await result.current.handleOpenInIDE('chat-empty', 'vscode');
    });

    expect(toast).toHaveBeenCalledWith({
      title: 'No messages to handoff',
      variant: 'default',
    });
    expect(desktopBridge.openExternal).not.toHaveBeenCalled();
  });

  it('reports export failures destructively', async () => {
    vi.mocked(exportChat).mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useChatActions([], mockT));

    await act(async () => {
      await result.current.handleOpenInIDE('chat-1', 'vscode');
    });

    expect(toast).toHaveBeenCalledWith({
      title: 'Failed to prepare IDE handoff',
      description: 'boom',
      variant: 'destructive',
    });
    expect(result.current.exportingId).toBeNull();
  });
});
