import { act, renderHook } from '@testing-library/react';
import { createElement } from 'react';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  pathname: '/',
}));

vi.mock('next/navigation', () => ({ usePathname: () => mocks.pathname }));
vi.mock('@/lib/utils/device', () => ({ checkIsMobile: () => false }));
vi.mock('@/hooks/ui/useResizableSidebar', () => ({
  useResizableSidebar: () => ({
    width: 280,
    isDragging: false,
    handleMouseDown: vi.fn(),
    handleDoubleClick: vi.fn(),
  }),
}));

import { useAppLayoutState } from '../useAppLayoutState';

const ROUTES_KEY = 'myrm_last_tab_routes';

function mountAt(pathname: string) {
  mocks.pathname = pathname;
  return renderHook(() => useAppLayoutState());
}

function goTo(view: ReturnType<typeof mountAt>, pathname: string) {
  mocks.pathname = pathname;
  view.rerender();
}

const rememberedRoutes = () => JSON.parse(localStorage.getItem(ROUTES_KEY) ?? 'null') as unknown;

describe('useAppLayoutState: tabs and remembered pages', () => {
  beforeEach(() => {
    localStorage.clear();
    mocks.pathname = '/';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders on the server without reading browser storage', () => {
    function Probe() {
      const { activeTab, lastChatUrl } = useAppLayoutState();
      return createElement('p', null, `${activeTab}:${lastChatUrl}`);
    }
    localStorage.setItem(ROUTES_KEY, JSON.stringify({ chat: '/c-9' }));
    vi.stubGlobal('window', undefined);

    try {
      expect(renderToString(createElement(Probe))).toContain('chat:null');
    } finally {
      vi.unstubAllGlobals();
    }
  });

  describe('which tab a page belongs to', () => {
    it.each([
      ['/', 'chat'],
      ['/c-42', 'chat'],
      ['/library', 'chat'],
      ['/work', 'work'],
      ['/work/task-1', 'work'],
      ['/projects', 'projects'],
      ['/projects/7', 'projects'],
      ['/kanban', 'projects'],
      ['/cron', 'projects'],
      ['/artifacts', 'projects'],
    ])('puts %s under the %s tab', (pathname, tab) => {
      expect(mountAt(pathname).result.current.activeTab).toBe(tab);
    });

    it('follows the viewer from page to page', () => {
      const view = mountAt('/');

      goTo(view, '/work/task-1');
      expect(view.result.current.activeTab).toBe('work');

      goTo(view, '/kanban');
      expect(view.result.current.activeTab).toBe('projects');

      goTo(view, '/c-1');
      expect(view.result.current.activeTab).toBe('chat');
    });

    it('lets a tab be picked before the page has moved, and keeps it until the page changes', () => {
      const view = mountAt('/');

      act(() => view.result.current.handleTabChange('work'));
      view.rerender();

      expect(view.result.current.activeTab).toBe('work');
    });
  });

  describe('remembering where each tab was left', () => {
    it('keeps the last page of every tab, in memory and in storage', () => {
      const view = mountAt('/c-1');
      goTo(view, '/work/a');
      goTo(view, '/kanban');
      goTo(view, '/c-2');

      expect(view.result.current).toMatchObject({
        lastChatUrl: '/c-2',
        lastWorkUrl: '/work/a',
        lastProjectsUrl: '/kanban',
      });
      expect(rememberedRoutes()).toEqual({ chat: '/c-2', work: '/work/a', projects: '/kanban' });
    });

    it.each(['/settings/system', '/library', '/pricing', '/library/abc-1'])(
      'does not remember %s as the place a tab was left',
      (pathname) => {
        const view = mountAt(pathname);

        expect(view.result.current).toMatchObject({ lastChatUrl: null, lastWorkUrl: null, lastProjectsUrl: null });
        expect(rememberedRoutes()).toBeNull();
      },
    );

    it('starts from the pages remembered by an earlier visit', () => {
      localStorage.setItem(ROUTES_KEY, JSON.stringify({ chat: '/c-9', work: '/work/z' }));

      const view = mountAt('/settings');

      expect(view.result.current).toMatchObject({ lastChatUrl: '/c-9', lastWorkUrl: '/work/z', lastProjectsUrl: null });
    });

    it('hands what one visit left to the next one', () => {
      const first = mountAt('/c-1');
      goTo(first, '/work/a');
      first.unmount();

      const next = mountAt('/settings');

      expect(next.result.current).toMatchObject({ lastChatUrl: '/c-1', lastWorkUrl: '/work/a', lastProjectsUrl: null });
    });

    it('adds to what is remembered instead of replacing it', () => {
      localStorage.setItem(ROUTES_KEY, JSON.stringify({ chat: '/c-9', projects: '/cron' }));

      mountAt('/work/z');

      expect(rememberedRoutes()).toEqual({ chat: '/c-9', projects: '/cron', work: '/work/z' });
    });

    it.each([
      ['unreadable JSON', '{broken json'],
      ['an empty value', ''],
      ['a JSON null', 'null'],
      ['a list', '["/c-1"]'],
      ['a number', '42'],
    ])('starts afresh when storage holds %s, without breaking the layout or keeping it', (_label, stored) => {
      localStorage.setItem(ROUTES_KEY, stored);

      const view = mountAt('/c-1');

      expect(view.result.current).toMatchObject({ lastChatUrl: '/c-1', lastWorkUrl: null, lastProjectsUrl: null });
      expect(rememberedRoutes()).toEqual({ chat: '/c-1' });
    });

    it('ignores a remembered page that does not belong to its tab', () => {
      localStorage.setItem(ROUTES_KEY, JSON.stringify({ chat: '/work/a', work: '/c-1', projects: '/kanban' }));

      const view = mountAt('/settings');

      expect(view.result.current).toMatchObject({ lastChatUrl: null, lastWorkUrl: null, lastProjectsUrl: '/kanban' });
    });

    it('ignores remembered entries that are not pages', () => {
      localStorage.setItem(ROUTES_KEY, JSON.stringify({ chat: 7, work: { url: '/work' }, projects: '/kanban' }));

      const view = mountAt('/settings');

      expect(view.result.current).toMatchObject({ lastChatUrl: null, lastWorkUrl: null, lastProjectsUrl: '/kanban' });
    });

    it('keeps working when the browser refuses to store the pages', () => {
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new DOMException('Quota exceeded', 'QuotaExceededError');
      });

      const view = mountAt('/c-1');

      expect(view.result.current.lastChatUrl).toBe('/c-1');
    });
  });
});
