/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  MAX_RECENT_DIRS,
  getRecentDirectoryPaths,
  rememberDirectoryPath,
  shortenHomePath,
} from '../directoryBrowseRecent';

const KEY = 'test.directoryBrowseRecent';

describe('directoryBrowseRecent', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('puts the latest pick first and moves a repeated pick to the front', () => {
    rememberDirectoryPath(KEY, '/a');
    rememberDirectoryPath(KEY, '/b');
    rememberDirectoryPath(KEY, '/a');

    expect(getRecentDirectoryPaths(KEY)).toEqual(['/a', '/b']);
  });

  it('keeps only the most recent entries', () => {
    for (let index = 0; index <= MAX_RECENT_DIRS; index += 1) {
      rememberDirectoryPath(KEY, `/dir-${index}`);
    }

    const recent = getRecentDirectoryPaths(KEY);
    expect(recent).toHaveLength(MAX_RECENT_DIRS);
    expect(recent[0]).toBe(`/dir-${MAX_RECENT_DIRS}`);
    expect(recent).not.toContain('/dir-0');
  });

  it('reads a missing, malformed or mistyped list as the strings it can use', () => {
    expect(getRecentDirectoryPaths(KEY)).toEqual([]);

    localStorage.setItem(KEY, '{not json');
    expect(getRecentDirectoryPaths(KEY)).toEqual([]);

    localStorage.setItem(KEY, JSON.stringify({ path: '/a' }));
    expect(getRecentDirectoryPaths(KEY)).toEqual([]);

    localStorage.setItem(KEY, JSON.stringify(['/a', 7, null, '/b']));
    expect(getRecentDirectoryPaths(KEY)).toEqual(['/a', '/b']);
  });

  it('does not throw when storage refuses the write, so the pick itself still succeeds', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError');
    });
    try {
      expect(() => rememberDirectoryPath(KEY, '/a')).not.toThrow();
    } finally {
      setItem.mockRestore();
    }
  });

  it('shortens the home folder on macOS, Linux and Windows', () => {
    expect(shortenHomePath('/Users/ada/projects/app')).toBe('~/projects/app');
    expect(shortenHomePath('/home/ada/projects/app')).toBe('~/projects/app');
    expect(shortenHomePath('C:\\Users\\ada\\projects\\app')).toBe('~\\projects\\app');
    expect(shortenHomePath('/srv/data')).toBe('/srv/data');
  });
});
