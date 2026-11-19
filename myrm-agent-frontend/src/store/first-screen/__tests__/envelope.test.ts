import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  SNAPSHOT_MAX_AGE_MS,
  flushSnapshot,
  readSnapshotSection,
  resetSnapshotForTests,
  writeSnapshotSection,
} from '../envelope';

const STORAGE_KEY = 'myrm-first-screen-snapshot';
const NOW = 1_800_000_000_000;

const stored = () => JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? 'null');
const envelopeOf = (overrides: Record<string, unknown> = {}) => ({
  schema: 1,
  build: 'dev',
  sections: { chatHistory: { savedAt: NOW, data: { filterKey: 'all', items: [] } } },
  ...overrides,
});

beforeEach(() => {
  vi.useFakeTimers();
  window.localStorage.clear();
  resetSnapshotForTests();
});

afterEach(() => {
  resetSnapshotForTests();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('writing', () => {
  it('stores a section one second after its first change', () => {
    writeSnapshotSection('projects', [{ id: 'p1' }], NOW);

    vi.advanceTimersByTime(999);
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();

    vi.advanceTimersByTime(1);
    expect(stored().sections.projects).toEqual({ savedAt: NOW, data: [{ id: 'p1' }] });
  });

  it('collapses writes inside the window into one write of the latest data', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');

    writeSnapshotSection('projects', [{ id: 'old' }], NOW);
    writeSnapshotSection('projects', [{ id: 'new' }], NOW + 5);
    expect(vi.getTimerCount()).toBe(1);
    vi.advanceTimersByTime(1_000);

    expect(setItem).toHaveBeenCalledTimes(1);
    expect(stored().sections.projects.data).toEqual([{ id: 'new' }]);
  });

  it('writes right away when the window is going away', () => {
    writeSnapshotSection('projects', [], NOW);

    flushSnapshot();

    expect(stored().sections.projects).toEqual({ savedAt: NOW, data: [] });
  });

  it('replaces only the sections this window wrote, so another window keeps its own', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(envelopeOf()));

    writeSnapshotSection('projects', [{ id: 'p1' }], NOW + 10);
    flushSnapshot();

    expect(stored().sections.chatHistory.data).toEqual({ filterKey: 'all', items: [] });
    expect(stored().sections.projects.data).toEqual([{ id: 'p1' }]);
  });

  it('starts a new envelope over one that another schema or build wrote', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(envelopeOf({ schema: 99 })));

    writeSnapshotSection('projects', [], NOW);
    flushSnapshot();

    expect(stored()).toEqual({ schema: 1, build: 'dev', sections: { projects: { savedAt: NOW, data: [] } } });
  });

  it('does nothing when there is nothing pending', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');

    flushSnapshot();

    expect(setItem).not.toHaveBeenCalled();
  });

  it('survives storage that refuses the write', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    writeSnapshotSection('projects', [], NOW);

    expect(() => flushSnapshot()).not.toThrow();
  });
});

describe('reading', () => {
  it('returns the data of a section that is current', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(envelopeOf()));

    expect(readSnapshotSection('chatHistory', NOW + 1_000)).toEqual({ filterKey: 'all', items: [] });
  });

  it('returns null for a section that was never stored', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(envelopeOf()));

    expect(readSnapshotSection('projects', NOW)).toBeNull();
  });

  it('ignores an envelope written by another schema or another build', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(envelopeOf({ schema: 2 })));
    expect(readSnapshotSection('chatHistory', NOW)).toBeNull();

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(envelopeOf({ build: 'v9.9.9' })));
    expect(readSnapshotSection('chatHistory', NOW)).toBeNull();
  });

  it('keeps a section up to the maximum age and drops it past that', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(envelopeOf()));

    expect(readSnapshotSection('chatHistory', NOW + SNAPSHOT_MAX_AGE_MS)).not.toBeNull();
    expect(readSnapshotSection('chatHistory', NOW + SNAPSHOT_MAX_AGE_MS + 1)).toBeNull();
  });

  it('does not trust a section dated in the future', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(envelopeOf()));

    expect(readSnapshotSection('chatHistory', NOW - 1)).toBeNull();
  });

  it.each([
    ['text that is not JSON', 'not json'],
    ['JSON that is not an envelope', '[1,2,3]'],
    ['sections of the wrong type', JSON.stringify({ schema: 1, build: 'dev', sections: 'x' })],
    [
      'a section without a timestamp',
      JSON.stringify({ schema: 1, build: 'dev', sections: { chatHistory: { data: 1 } } }),
    ],
  ])('ignores %s', (_label, raw) => {
    window.localStorage.setItem(STORAGE_KEY, raw);

    expect(readSnapshotSection('chatHistory', NOW)).toBeNull();
  });

  it('survives storage that refuses the read', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError');
    });

    expect(readSnapshotSection('chatHistory', NOW)).toBeNull();
  });
});
