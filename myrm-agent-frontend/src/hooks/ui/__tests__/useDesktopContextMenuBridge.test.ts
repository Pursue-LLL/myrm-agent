import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  isDesktopEnvironment,
  dispatchDesktopContextMenu,
  useDesktopContextMenuBridge,
  DESKTOP_CONTEXT_MENU_EVENT,
} from '../useDesktopContextMenuBridge';

describe('useDesktopContextMenuBridge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete (window as unknown as { __TAURI__?: unknown }).__TAURI__;
  });

  afterEach(() => {
    delete (window as unknown as { __TAURI__?: unknown }).__TAURI__;
  });

  it('detects desktop environment correctly', () => {
    expect(isDesktopEnvironment()).toBe(false);

    (window as unknown as { __TAURI__: unknown }).__TAURI__ = {};
    expect(isDesktopEnvironment()).toBe(true);
  });

  it('dispatches desktop context menu event on window', () => {
    const listener = vi.fn();
    window.addEventListener(DESKTOP_CONTEXT_MENU_EVENT, listener);

    const detail = {
      sessionId: 'sess-101',
      title: 'Debug task',
      clientX: 120,
      clientY: 240,
      source: 'session_row' as const,
    };

    dispatchDesktopContextMenu(detail);

    expect(listener).toHaveBeenCalledTimes(1);
    const event = listener.mock.calls[0][0] as CustomEvent;
    expect(event.detail.sessionId).toBe('sess-101');
    expect(event.detail.clientX).toBe(120);

    window.removeEventListener(DESKTOP_CONTEXT_MENU_EVENT, listener);
  });

  it('calls webFallback on context menu event in browser mode', () => {
    const fallbackMock = vi.fn();
    const { result } = renderHook(() =>
      useDesktopContextMenuBridge({ onWebFallback: fallbackMock }),
    );

    const preventDefault = vi.fn();
    const mockMouseEvent = {
      clientX: 50,
      clientY: 100,
      preventDefault,
    } as unknown as React.MouseEvent;

    act(() => {
      result.current.handleContextMenu(mockMouseEvent, {
        sessionId: 'sess-fallback',
        title: 'Title',
        source: 'session_row',
      });
    });

    expect(preventDefault).toHaveBeenCalled();
    expect(fallbackMock).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: 'sess-fallback',
        clientX: 50,
        clientY: 100,
      }),
    );
  });

  it('prevents default and dispatches custom event in desktop mode', () => {
    (window as unknown as { __TAURI__: unknown }).__TAURI__ = {};
    const listener = vi.fn();
    window.addEventListener(DESKTOP_CONTEXT_MENU_EVENT, listener);

    const { result } = renderHook(() => useDesktopContextMenuBridge());
    const preventDefault = vi.fn();
    const mockMouseEvent = {
      clientX: 200,
      clientY: 300,
      preventDefault,
    } as unknown as React.MouseEvent;

    act(() => {
      result.current.handleContextMenu(mockMouseEvent, {
        sessionId: 'sess-desktop',
        title: 'Desktop Title',
        source: 'session_row',
      });
    });

    expect(preventDefault).toHaveBeenCalled();
    expect(listener).toHaveBeenCalled();

    window.removeEventListener(DESKTOP_CONTEXT_MENU_EVENT, listener);
  });
});
