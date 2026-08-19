import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { normalizeDesktopPath, useDesktopFolderDrop } from '../useDesktopFolderDrop';
import * as tauriLib from '@/lib/tauri';
import * as chatService from '@/services/chat';
import * as sessionAccessRefresh from '@/lib/sessionAccessRefresh';
import useChatStore from '@/store/useChatStore';

const mockToast = vi.hoisted(() => ({
  warning: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
}));
vi.mock('@/lib/utils/toast', () => ({ toast: mockToast }));
vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock('@/lib/tauri', () => ({
  isTauriEnvironment: vi.fn(),
  listenTauriEvent: vi.fn(),
}));

vi.mock('@/services/chat', () => ({
  grantSessionAccessRoot: vi.fn(),
}));

vi.mock('@/lib/sessionAccessRefresh', () => ({
  refreshSessionAccessRoots: vi.fn(),
}));

describe('normalizeDesktopPath', () => {
  it('converts Windows backslashes to forward slashes', () => {
    expect(normalizeDesktopPath('C:\\Users\\John\\Documents')).toBe('C:/Users/John/Documents');
  });

  it('removes redundant trailing slashes except for root', () => {
    expect(normalizeDesktopPath('/Users/alice/project/')).toBe('/Users/alice/project');
    expect(normalizeDesktopPath('/')).toBe('/');
    expect(normalizeDesktopPath('C:/')).toBe('C:/');
  });

  it('handles multiple consecutive slashes', () => {
    expect(normalizeDesktopPath('/Users//bob///work/')).toBe('/Users/bob/work');
  });

  it('returns empty string for blank input', () => {
    expect(normalizeDesktopPath('   ')).toBe('');
  });
});

describe('useDesktopFolderDrop', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({
      chatId: 'test-chat-123',
      sessionAccessRoots: [],
    });
  });

  it('does not register Tauri listeners if not in Tauri environment', () => {
    (tauriLib.isTauriEnvironment as unknown as { mockReturnValue: (v: boolean) => void }).mockReturnValue(false);

    renderHook(() => useDesktopFolderDrop());

    expect(tauriLib.listenTauriEvent).not.toHaveBeenCalled();
  });

  it('registers Tauri drag-drop listeners when in Tauri environment', async () => {
    (tauriLib.isTauriEnvironment as unknown as { mockReturnValue: (v: boolean) => void }).mockReturnValue(true);
    const unlistenMock = vi.fn();
    (tauriLib.listenTauriEvent as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue(unlistenMock);

    const { unmount } = renderHook(() => useDesktopFolderDrop());

    expect(tauriLib.listenTauriEvent).toHaveBeenCalledWith('tauri://drag-drop', expect.any(Function));
    expect(tauriLib.listenTauriEvent).toHaveBeenCalledWith('tauri://drag-enter', expect.any(Function));
    expect(tauriLib.listenTauriEvent).toHaveBeenCalledWith('tauri://drag-leave', expect.any(Function));

    unmount();
    expect(unlistenMock).toHaveBeenCalled();
  });

  it('grants session access root and refreshes store on dropped paths', async () => {
    (tauriLib.isTauriEnvironment as unknown as { mockReturnValue: (v: boolean) => void }).mockReturnValue(true);
    (chatService.grantSessionAccessRoot as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({
      session_access_roots: [
        { path: '/Users/test/workspace', writable: true, source: 'desktop_drag_drop' },
      ],
    });

    const onGranted = vi.fn();
    const { result } = renderHook(() =>
      useDesktopFolderDrop({ onFolderGranted: onGranted }),
    );

    await act(async () => {
      await result.current.handleDroppedPaths(['/Users/test/workspace/']);
    });

    expect(chatService.grantSessionAccessRoot).toHaveBeenCalledWith(
      'test-chat-123',
      '/Users/test/workspace',
      true,
    );
    expect(sessionAccessRefresh.refreshSessionAccessRoots).toHaveBeenCalledWith(
      'test-chat-123',
      {
        optimistic: {
          path: '/Users/test/workspace',
          writable: true,
          source: 'desktop_drag_drop',
        },
      },
    );
    expect(onGranted).toHaveBeenCalledWith('/Users/test/workspace');
  });
});
