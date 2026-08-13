/**
 * Tests that releaseTurnInspectorControls releases both desktop + browser
 * inspector turn engagement via dynamic imports, and swallows import failures.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockDesktopReleaseTurnEngagement = vi.fn();
const mockBrowserReleaseTurnEngagement = vi.fn();

vi.mock('@/store/useDesktopInspectorStore', () => ({
  default: {
    getState: vi.fn(() => ({ releaseTurnEngagement: mockDesktopReleaseTurnEngagement })),
  },
}));

vi.mock('@/store/useBrowserInspectorStore', () => ({
  default: {
    getState: () => ({ releaseTurnEngagement: mockBrowserReleaseTurnEngagement }),
  },
}));

import { releaseTurnInspectorControls } from '../releaseTurnInspectorControls';

describe('releaseTurnInspectorControls', () => {
  beforeEach(() => {
    mockDesktopReleaseTurnEngagement.mockClear();
    mockBrowserReleaseTurnEngagement.mockClear();
  });

  it('releases turn engagement on both desktop and browser inspectors', async () => {
    await releaseTurnInspectorControls('c1');

    expect(mockDesktopReleaseTurnEngagement).toHaveBeenCalledTimes(1);
    expect(mockDesktopReleaseTurnEngagement).toHaveBeenCalledWith('c1');
    expect(mockBrowserReleaseTurnEngagement).toHaveBeenCalledTimes(1);
    expect(mockBrowserReleaseTurnEngagement).toHaveBeenCalledWith('c1');
  });

  it('swallows store access failures without rejecting', async () => {
    const { default: useDesktopInspectorStore } = await import('@/store/useDesktopInspectorStore');
    vi.mocked(useDesktopInspectorStore.getState).mockImplementationOnce(() => {
      throw new Error('store access failed');
    });

    await expect(releaseTurnInspectorControls('c1')).resolves.toBeUndefined();
  });
});
