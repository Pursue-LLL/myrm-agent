import { describe, it, expect, beforeEach, vi } from 'vitest';

const ROUTE_STORAGE_KEY = 'myrm_last_tab_routes';

function readSavedRoutes(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  try {
    return JSON.parse(localStorage.getItem(ROUTE_STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
}

function persistRoute(tab: string, url: string) {
  if (typeof window === 'undefined') return;
  try {
    const saved = readSavedRoutes();
    saved[tab] = url;
    localStorage.setItem(ROUTE_STORAGE_KEY, JSON.stringify(saved));
  } catch {
    /* quota exceeded — non-critical */
  }
}

describe('Route Persistence', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  describe('readSavedRoutes', () => {
    it('returns empty object when no saved routes', () => {
      expect(readSavedRoutes()).toEqual({});
    });

    it('reads saved routes from localStorage', () => {
      const routes = { chat: '/c-abc123', work: '/work/task-1', projects: '/kanban' };
      localStorage.setItem(ROUTE_STORAGE_KEY, JSON.stringify(routes));
      expect(readSavedRoutes()).toEqual(routes);
    });

    it('returns empty object on malformed JSON', () => {
      localStorage.setItem(ROUTE_STORAGE_KEY, '{broken json!!!');
      expect(readSavedRoutes()).toEqual({});
    });

    it('returns empty object when value is empty string', () => {
      localStorage.setItem(ROUTE_STORAGE_KEY, '');
      expect(readSavedRoutes()).toEqual({});
    });
  });

  describe('persistRoute', () => {
    it('persists a single route', () => {
      persistRoute('chat', '/c-xyz');
      const raw = localStorage.getItem(ROUTE_STORAGE_KEY);
      expect(raw).not.toBeNull();
      expect(JSON.parse(raw!)).toEqual({ chat: '/c-xyz' });
    });

    it('preserves existing routes when adding new', () => {
      persistRoute('chat', '/c-abc');
      persistRoute('work', '/work/task-2');
      const raw = localStorage.getItem(ROUTE_STORAGE_KEY);
      expect(JSON.parse(raw!)).toEqual({ chat: '/c-abc', work: '/work/task-2' });
    });

    it('overwrites existing route for same tab', () => {
      persistRoute('chat', '/c-old');
      persistRoute('chat', '/c-new');
      const raw = localStorage.getItem(ROUTE_STORAGE_KEY);
      expect(JSON.parse(raw!)).toEqual({ chat: '/c-new' });
    });

    it('handles all three tabs', () => {
      persistRoute('chat', '/');
      persistRoute('work', '/agents');
      persistRoute('projects', '/artifacts');
      const raw = localStorage.getItem(ROUTE_STORAGE_KEY);
      expect(JSON.parse(raw!)).toEqual({
        chat: '/',
        work: '/agents',
        projects: '/artifacts',
      });
    });

    it('gracefully handles quota exceeded', () => {
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new DOMException('QuotaExceededError');
      });
      expect(() => persistRoute('chat', '/c-quota')).not.toThrow();
      vi.restoreAllMocks();
    });
  });

  describe('round-trip', () => {
    it('readSavedRoutes returns what persistRoute wrote', () => {
      persistRoute('chat', '/c-round');
      persistRoute('work', '/work/round');
      persistRoute('projects', '/projects/round');
      expect(readSavedRoutes()).toEqual({
        chat: '/c-round',
        work: '/work/round',
        projects: '/projects/round',
      });
    });
  });
});
