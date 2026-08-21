/**
 * @vitest-environment jsdom
 * Tests for useScrollPositionRestore (AutoScrollFollowPersistenceMirror)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useScrollPositionRestore } from '../useScrollPositionRestore';

describe('useScrollPositionRestore (AutoScrollFollowPersistenceMirror)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    window.scrollY = 0;
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('initializes with default follower flags when no mirror exists', () => {
    const { result } = renderHook(() =>
      useScrollPositionRestore({
        id: 'chat-123',
        enabled: true,
      }),
    );

    expect(result.current.userScrolledRef.current).toBe(false);
    expect(result.current.isFollowingBottomRef.current).toBe(true);
    expect(result.current.getScrollMirrorSnapshot()).toBeNull();
  });

  it('saves and restores window scroll position and following state correctly', () => {
    const { result, unmount } = renderHook(() =>
      useScrollPositionRestore({
        id: 'chat-123',
        enabled: true,
      }),
    );

    act(() => {
      result.current.saveScrollPosition({
        position: 450,
        isFollowingBottom: false,
        isUserScrolledUp: true,
        anchorMessageId: 'msg-42',
      });
    });

    const snapshot = result.current.getScrollMirrorSnapshot();
    expect(snapshot).not.toBeNull();
    expect(snapshot?.position).toBe(450);
    expect(snapshot?.isFollowingBottom).toBe(false);
    expect(snapshot?.isUserScrolledUp).toBe(true);
    expect(snapshot?.anchorMessageId).toBe('msg-42');

    unmount();

    // Re-mount in new hook instance
    const onRestore = vi.fn();
    const { result: newResult } = renderHook(() =>
      useScrollPositionRestore({
        id: 'chat-123',
        enabled: true,
        onRestore,
      }),
    );

    act(() => {
      const restored = newResult.current.restoreScrollPosition();
      expect(restored).toBe(true);
    });

    expect(newResult.current.userScrolledRef.current).toBe(true);
    expect(newResult.current.isFollowingBottomRef.current).toBe(false);
    expect(onRestore).toHaveBeenCalledWith(
      expect.objectContaining({
        position: 450,
        isFollowingBottom: false,
        isUserScrolledUp: true,
        anchorMessageId: 'msg-42',
      }),
    );
  });

  it('supports custom virtual container getScrollElement', () => {
    const mockElement = {
      scrollTop: 1200,
      scrollHeight: 3000,
      clientHeight: 800,
    } as unknown as HTMLElement;

    const getScrollElement = vi.fn(() => mockElement);

    const { result } = renderHook(() =>
      useScrollPositionRestore({
        id: 'virtual-chat-999',
        enabled: true,
        getScrollElement,
      }),
    );

    act(() => {
      result.current.saveScrollPosition({
        position: 1200,
        isFollowingBottom: false,
        isUserScrolledUp: true,
        anchorMessageId: 'virtual-msg-10',
      });
    });

    expect(result.current.getScrollMirrorSnapshot()?.position).toBe(1200);
    expect(result.current.getScrollMirrorSnapshot()?.anchorMessageId).toBe('virtual-msg-10');

    // Restore on custom element
    act(() => {
      result.current.restoreScrollPosition();
    });

    expect(result.current.userScrolledRef.current).toBe(true);
    expect(result.current.isFollowingBottomRef.current).toBe(false);
  });

  it('maintains LRU cache limit in sessionStorage across multiple chats', () => {
    // Save 12 chats (limit is 10)
    for (let i = 1; i <= 12; i++) {
      const { result } = renderHook(() =>
        useScrollPositionRestore({
          id: `chat-lru-${i}`,
          enabled: true,
        }),
      );

      act(() => {
        result.current.saveScrollPosition({
          position: i * 100,
          isFollowingBottom: i % 2 === 0,
          isUserScrolledUp: i % 2 !== 0,
        });
      });
    }

    const storedKeys = Object.keys(sessionStorage).filter((k) => k.startsWith('myrm_scroll_mirror_'));
    expect(storedKeys.length).toBeLessThanOrEqual(10);
  });
});
