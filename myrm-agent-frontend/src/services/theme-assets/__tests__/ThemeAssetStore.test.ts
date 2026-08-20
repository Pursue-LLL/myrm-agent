import { describe, expect, it, vi, afterEach } from 'vitest';
import { verifyThemeAssetAvailable } from '@/services/theme-assets/ThemeAssetStore';

describe('verifyThemeAssetAvailable', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns true for null assetRef', async () => {
    await expect(verifyThemeAssetAvailable(null)).resolves.toBe(true);
  });

  it('returns false when HEAD reports missing file', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    await expect(verifyThemeAssetAvailable('file:missing')).resolves.toBe(false);
  });

  it('falls back to ranged GET when HEAD is not allowed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce({ ok: false, status: 405 }).mockResolvedValueOnce({ ok: true, status: 206 }),
    );
    await expect(verifyThemeAssetAvailable('file:hero')).resolves.toBe(true);
  });
});
