import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { elapse, startFakeClock, stopFakeClock } from '@/test-utils/fakeClock';

const mocks = vi.hoisted(() => ({
  pathname: '/',
  isPhone: false,
  isRemoteSurface: false,
  sidebarWidth: 280,
  collapseSidebar: undefined as (() => void) | undefined,
  checkIsMobile: vi.fn<() => boolean>(),
  isMobileRemotePath: vi.fn<(pathname: string) => boolean>(),
  cancelAllRequests: vi.fn(),
  resizeStart: vi.fn(),
  resizeReset: vi.fn(),
}));

vi.mock('next/navigation', () => ({ usePathname: () => mocks.pathname }));
vi.mock('@/lib/utils/device', () => ({ checkIsMobile: mocks.checkIsMobile }));
vi.mock('@/lib/utils/requestManager', () => ({ requestManager: { cancelAllRequests: mocks.cancelAllRequests } }));
vi.mock('@/lib/mobileRemote', () => ({ isMobileRemotePath: mocks.isMobileRemotePath }));
vi.mock('@/hooks/ui/useResizableSidebar', () => ({
  useResizableSidebar: (options?: { onCollapse?: () => void }) => {
    mocks.collapseSidebar = options?.onCollapse;
    return {
      width: mocks.sidebarWidth,
      isDragging: false,
      handleMouseDown: mocks.resizeStart,
      handleDoubleClick: mocks.resizeReset,
    };
  },
}));

import { NAVBAR_WIDTH, useAppLayoutState } from '../useAppLayoutState';

const originalScrollY = Object.getOwnPropertyDescriptor(window, 'scrollY');

function mountAt(pathname: string) {
  mocks.pathname = pathname;
  return renderHook(() => useAppLayoutState());
}

describe('useAppLayoutState: layout, sidebar and phone behaviour', () => {
  beforeEach(() => {
    localStorage.clear();
    mocks.pathname = '/';
    mocks.isPhone = false;
    mocks.isRemoteSurface = false;
    mocks.sidebarWidth = 280;
    mocks.collapseSidebar = undefined;
    mocks.checkIsMobile.mockReset().mockImplementation(() => mocks.isPhone);
    mocks.isMobileRemotePath.mockReset().mockImplementation(() => mocks.isRemoteSurface);
    mocks.cancelAllRequests.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    if (originalScrollY) {
      Object.defineProperty(window, 'scrollY', originalScrollY);
    }
  });

  describe('the sidebar next to the chat', () => {
    it('reserves room for the rail and the sidebar', () => {
      const view = mountAt('/');

      expect(view.result.current.showMobileLayout).toBe(false);
      expect(view.result.current.isSidebarCollapsed).toBe(false);
      expect(view.result.current.shouldShowContentSidebar).toBe(true);
      expect(view.result.current.paddingLeft).toBe(`${NAVBAR_WIDTH + 280}px`);
      expect(view.result.current.sidebarWidth).toBe(280);
    });

    it('reserves room for the rail only while the sidebar is folded, and again once it is opened', () => {
      const view = mountAt('/');

      act(() => view.result.current.handleToggleSidebar());
      expect(view.result.current.isSidebarCollapsed).toBe(true);
      expect(view.result.current.paddingLeft).toBe(`${NAVBAR_WIDTH}px`);

      act(() => view.result.current.handleToggleSidebar());
      expect(view.result.current.paddingLeft).toBe(`${NAVBAR_WIDTH + 280}px`);
    });

    it('follows the width the viewer drags the sidebar to', () => {
      mocks.sidebarWidth = 340;

      expect(mountAt('/').result.current.paddingLeft).toBe(`${NAVBAR_WIDTH + 340}px`);
    });

    it('folds when the viewer drags the sidebar shut', () => {
      const view = mountAt('/');

      act(() => mocks.collapseSidebar?.());

      expect(view.result.current.isSidebarCollapsed).toBe(true);
    });

    it('hands the drag handlers of the resizable sidebar to the layout', () => {
      const { result } = mountAt('/');

      expect(result.current.handleSidebarResizeStart).toBe(mocks.resizeStart);
      expect(result.current.handleSidebarDoubleClick).toBe(mocks.resizeReset);
    });

    it.each(['/work', '/projects', '/research', '/settings/system'])(
      'has no sidebar next to %s, only the rail',
      (pathname) => {
        const view = mountAt(pathname);

        expect(view.result.current.shouldShowContentSidebar).toBe(false);
        expect(view.result.current.paddingLeft).toBe(`${NAVBAR_WIDTH}px`);
      },
    );
  });

  describe('what kind of page it is', () => {
    it('recognises the settings pages', () => {
      expect(mountAt('/settings/system').result.current.isSettingsPage).toBe(true);
      expect(mountAt('/').result.current.isSettingsPage).toBe(false);
    });

    it('recognises the research workbench, and only that exact page', () => {
      expect(mountAt('/research').result.current.isResearchPage).toBe(true);
      expect(mountAt('/research-notes').result.current.isResearchPage).toBe(false);
      expect(mountAt('/').result.current.isResearchPage).toBe(false);
    });

    it('asks the phone-remote check about the current page', () => {
      mocks.isRemoteSurface = true;

      const view = mountAt('/mobile/board');

      expect(view.result.current.isRemoteSurface).toBe(true);
      expect(mocks.isMobileRemotePath).toHaveBeenCalledWith('/mobile/board');
    });
  });

  describe('on a phone', () => {
    beforeEach(() => {
      mocks.isPhone = true;
    });

    it('uses the phone layout with the sidebar folded away and no room reserved for it', () => {
      const { result } = mountAt('/');

      expect(result.current.showMobileLayout).toBe(true);
      expect(result.current.isSidebarCollapsed).toBe(true);
      expect(result.current.paddingLeft).toBe('0px');
    });

    it('opens and closes the sidebar drawer', () => {
      const { result } = mountAt('/');
      expect(result.current.isMobileSidebarOpen).toBe(false);

      act(() => result.current.setIsMobileSidebarOpen(true));

      expect(result.current.isMobileSidebarOpen).toBe(true);
    });
  });

  describe('when the window is resized', () => {
    beforeEach(startFakeClock);
    afterEach(stopFakeClock);

    it('switches layout once the resizing has settled, not on every event', async () => {
      const { result } = mountAt('/');
      expect(mocks.checkIsMobile).toHaveBeenCalledTimes(1);
      mocks.isPhone = true;

      for (let burst = 0; burst < 3; burst += 1) {
        act(() => {
          window.dispatchEvent(new Event('resize'));
        });
        await elapse(60);
      }
      expect(result.current.showMobileLayout).toBe(false);

      await elapse(100);

      expect(result.current.showMobileLayout).toBe(true);
      expect(result.current.isSidebarCollapsed).toBe(true);
      expect(mocks.checkIsMobile).toHaveBeenCalledTimes(3);
    });

    it('returns to the desktop layout when the window grows again', async () => {
      mocks.isPhone = true;
      const { result } = mountAt('/');
      mocks.isPhone = false;

      act(() => {
        window.dispatchEvent(new Event('resize'));
      });
      await elapse(100);

      expect(result.current.showMobileLayout).toBe(false);
    });

    it('stops listening, and drops a check still waiting, once the layout is gone', async () => {
      const { unmount } = mountAt('/');
      act(() => {
        window.dispatchEvent(new Event('resize'));
      });
      unmount();
      mocks.checkIsMobile.mockClear();

      await elapse(200);
      act(() => {
        window.dispatchEvent(new Event('resize'));
      });
      await elapse(200);

      expect(mocks.checkIsMobile).not.toHaveBeenCalled();
    });
  });

  describe('the menu button on a phone while scrolling', () => {
    beforeEach(() => {
      startFakeClock();
      mocks.isPhone = true;
    });
    afterEach(stopFakeClock);

    const scrollTo = (position: number) =>
      act(() => {
        Object.defineProperty(window, 'scrollY', { configurable: true, value: position });
        window.dispatchEvent(new Event('scroll'));
      });

    it('slips away when scrolling down past the header, and returns when scrolling back up', () => {
      const { result } = mountAt('/');

      scrollTo(150);
      expect(result.current.isNavButtonHidden).toBe(true);

      scrollTo(120);
      expect(result.current.isNavButtonHidden).toBe(false);
    });

    it('stays put while the page is still near the top', () => {
      const { result } = mountAt('/');

      scrollTo(90);
      expect(result.current.isNavButtonHidden).toBe(false);

      scrollTo(300);
      expect(result.current.isNavButtonHidden).toBe(true);
      scrollTo(40);
      expect(result.current.isNavButtonHidden).toBe(false);
    });

    it('ignores nudges of ten pixels or less, whichever way the button is', () => {
      const { result } = mountAt('/');
      scrollTo(300);
      expect(result.current.isNavButtonHidden).toBe(true);
      scrollTo(295);
      expect(result.current.isNavButtonHidden).toBe(true);

      scrollTo(150);
      expect(result.current.isNavButtonHidden).toBe(false);
      scrollTo(155);
      expect(result.current.isNavButtonHidden).toBe(false);
    });

    it('comes back by itself a moment after scrolling stops', async () => {
      const { result } = mountAt('/');
      scrollTo(300);
      expect(result.current.isNavButtonHidden).toBe(true);

      await elapse(1499);
      expect(result.current.isNavButtonHidden).toBe(true);

      await elapse(1);
      expect(result.current.isNavButtonHidden).toBe(false);
    });

    it('waits the full moment again after each scroll', async () => {
      const { result } = mountAt('/');
      scrollTo(300);
      await elapse(1000);
      scrollTo(400);
      await elapse(1000);

      expect(result.current.isNavButtonHidden).toBe(true);

      await elapse(500);
      expect(result.current.isNavButtonHidden).toBe(false);
    });

    it('is left alone on a desktop screen', () => {
      mocks.isPhone = false;
      const { result } = mountAt('/');

      scrollTo(300);

      expect(result.current.isNavButtonHidden).toBe(false);
    });

    it('lets go of the scroll listener and the pending timer once the layout is gone', () => {
      const removed = vi.spyOn(window, 'removeEventListener');
      const { unmount } = mountAt('/');
      scrollTo(300);
      expect(vi.getTimerCount()).toBe(1);

      unmount();

      expect(removed).toHaveBeenCalledWith('scroll', expect.any(Function));
      expect(vi.getTimerCount()).toBe(0);
    });
  });

  it('cancels the requests still in flight when the layout goes away', () => {
    const { unmount } = mountAt('/');
    expect(mocks.cancelAllRequests).not.toHaveBeenCalled();

    unmount();

    expect(mocks.cancelAllRequests).toHaveBeenCalledTimes(1);
  });
});
