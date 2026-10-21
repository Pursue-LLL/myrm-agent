import { afterEach, describe, expect, it, vi } from 'vitest';
import { waitForThemeListingOwnership } from '@/services/themeMarketplace';

describe('waitForThemeListingOwnership', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('returns listing when entitlement becomes owned', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 't1', is_owned: false, install_count: 0, status: 'published' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 't1',
          is_owned: true,
          name: 'Neon',
          install_count: 0,
          status: 'published',
        }),
      });
    vi.stubGlobal('fetch', fetchMock);

    vi.spyOn(window, 'setTimeout').mockImplementation((handler: TimerHandler) => {
      if (typeof handler === 'function') {
        handler();
      }
      return 0 as unknown as ReturnType<typeof setTimeout>;
    });

    const listing = await waitForThemeListingOwnership('t1', { attempts: 2, delayMs: 0 });
    expect(listing.isOwned).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
