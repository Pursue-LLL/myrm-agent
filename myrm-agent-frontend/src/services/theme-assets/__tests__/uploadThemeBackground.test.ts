import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  ThemeBackgroundValidationFailedError,
  uploadThemeBackground,
} from '@/services/theme-assets/uploadThemeBackground';
import { uploadThemeAsset } from '@/services/theme-assets/uploadThemeAsset';
import { extractVideoPosterBlob, VideoPosterExtractionError } from '@/services/theme-assets/extractVideoPoster';

vi.mock('@/services/theme-assets/uploadThemeAsset', () => ({
  uploadThemeAsset: vi.fn(),
}));

vi.mock('@/services/theme-assets/extractVideoPoster', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/theme-assets/extractVideoPoster')>();
  return {
    ...actual,
    extractVideoPosterBlob: vi.fn(),
  };
});

describe('uploadThemeBackground', () => {
  beforeEach(() => {
    vi.mocked(uploadThemeAsset).mockReset();
    vi.mocked(extractVideoPosterBlob).mockReset();
  });

  it('uploads image and returns file: assetRef', async () => {
    vi.mocked(uploadThemeAsset).mockResolvedValue({
      fileId: 'img-1',
      fileName: 'hero.png',
      fileUrl: 'https://example.com/img-1',
      mimeType: 'image/png',
    });

    const file = new File(['pixels'], 'hero.png', { type: 'image/png' });
    const result = await uploadThemeBackground(file);

    expect(result).toEqual({
      assetRef: 'file:img-1',
      mediaKind: 'image',
      posterAssetRef: null,
    });
    expect(uploadThemeAsset).toHaveBeenCalledTimes(1);
    expect(extractVideoPosterBlob).not.toHaveBeenCalled();
  });

  it('extracts poster before parallel video upload', async () => {
    vi.mocked(extractVideoPosterBlob).mockResolvedValue(new Blob(['jpeg'], { type: 'image/jpeg' }));
    vi.mocked(uploadThemeAsset)
      .mockResolvedValueOnce({
        fileId: 'vid-1',
        fileName: 'loop.mp4',
        fileUrl: 'https://example.com/vid-1',
        mimeType: 'video/mp4',
      })
      .mockResolvedValueOnce({
        fileId: 'poster-1',
        fileName: 'loop-poster.jpg',
        fileUrl: 'https://example.com/poster-1',
        mimeType: 'image/jpeg',
      });

    const file = new File(['video'], 'loop.mp4', { type: 'video/mp4' });
    const result = await uploadThemeBackground(file);

    expect(result).toEqual({
      assetRef: 'file:vid-1',
      mediaKind: 'video',
      posterAssetRef: 'file:poster-1',
    });
    expect(extractVideoPosterBlob).toHaveBeenCalledWith(file);
    expect(uploadThemeAsset).toHaveBeenCalledTimes(2);
    const posterCall = vi.mocked(uploadThemeAsset).mock.calls[1]?.[0];
    expect(posterCall?.name).toBe('loop-poster.jpg');
    expect(posterCall?.type).toBe('image/jpeg');
  });

  it('throws validation error for unsupported files', async () => {
    const file = new File(['x'], 'notes.txt', { type: 'text/plain' });
    await expect(uploadThemeBackground(file)).rejects.toBeInstanceOf(
      ThemeBackgroundValidationFailedError,
    );
    expect(uploadThemeAsset).not.toHaveBeenCalled();
  });

  it('propagates poster extraction failures without uploading', async () => {
    vi.mocked(extractVideoPosterBlob).mockRejectedValue(
      new VideoPosterExtractionError('Failed to load video for poster extraction'),
    );

    const file = new File(['video'], 'loop.mp4', { type: 'video/mp4' });
    await expect(uploadThemeBackground(file)).rejects.toBeInstanceOf(VideoPosterExtractionError);
    expect(uploadThemeAsset).not.toHaveBeenCalled();
  });
});
