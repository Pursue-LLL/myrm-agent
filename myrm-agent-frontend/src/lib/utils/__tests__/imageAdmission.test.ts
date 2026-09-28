/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { admitAndCompressImageFile, admitAndCompressFiles } from '../imageAdmission';

describe('imageAdmission', () => {
  const originalCreateImageBitmap = globalThis.createImageBitmap;
  const originalOffscreenCanvas = globalThis.OffscreenCanvas;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.createImageBitmap = originalCreateImageBitmap;
    globalThis.OffscreenCanvas = originalOffscreenCanvas;
  });

  it('passes through non-image files intact without inspection', async () => {
    const textFile = new File(['hello world'], 'report.txt', { type: 'text/plain' });
    const result = await admitAndCompressImageFile(textFile);
    expect(result).toBe(textFile);
  });

  it('passes through SVG and GIF files to preserve vector graphics and animation frames', async () => {
    const svgFile = new File(['<svg></svg>'], 'icon.svg', { type: 'image/svg+xml' });
    const gifFile = new File(['GIF89a'], 'animation.gif', { type: 'image/gif' });

    expect(await admitAndCompressImageFile(svgFile)).toBe(svgFile);
    expect(await admitAndCompressImageFile(gifFile)).toBe(gifFile);
  });

  it('bypasses compression when image dimension and file size are within limits', async () => {
    const smallFile = new File([new Uint8Array(1024)], 'photo.png', { type: 'image/png' });
    const mockBitmap = {
      width: 800,
      height: 600,
      close: vi.fn(),
    } as unknown as ImageBitmap;

    globalThis.createImageBitmap = vi.fn().mockResolvedValue(mockBitmap);

    const result = await admitAndCompressImageFile(smallFile);
    expect(result).toBe(smallFile);
    expect(mockBitmap.close).toHaveBeenCalled();
  });

  it('downscales and converts oversized dimension image (e.g., 4000x2000) to webp', async () => {
    const largeDimFile = new File([new Uint8Array(2000)], 'huge.png', { type: 'image/png' });
    const mockBitmap = {
      width: 4000,
      height: 2000,
      close: vi.fn(),
    } as unknown as ImageBitmap;

    globalThis.createImageBitmap = vi.fn().mockResolvedValue(mockBitmap);

    const drawImageSpy = vi.fn();
    const convertToBlobSpy = vi.fn().mockResolvedValue(new Blob([new Uint8Array(500)], { type: 'image/webp' }));

    class MockOffscreenCanvas {
      width: number;
      height: number;
      constructor(width: number, height: number) {
        this.width = width;
        this.height = height;
      }
      getContext() {
        return {
          drawImage: drawImageSpy,
        };
      }
      convertToBlob = convertToBlobSpy;
    }

    globalThis.OffscreenCanvas = MockOffscreenCanvas as unknown as typeof OffscreenCanvas;

    const result = await admitAndCompressImageFile(largeDimFile);

    expect(result).not.toBe(largeDimFile);
    expect(result.name).toBe('huge.webp');
    expect(result.type).toBe('image/webp');
    // 4000x2000 等比缩小到 maxDimension=2048 -> 2048x1024
    expect(drawImageSpy).toHaveBeenCalledWith(mockBitmap, 0, 0, 2048, 1024);
    expect(mockBitmap.close).toHaveBeenCalled();
  });

  it('compresses file exceeding maxFileSizeBytes even if dimensions are moderate', async () => {
    // 模拟 5MB 文件
    const oversizedBlob = new Uint8Array(5 * 1024 * 1024);
    const heavyFile = new File([oversizedBlob], 'render.jpeg', { type: 'image/jpeg' });
    const mockBitmap = {
      width: 1920,
      height: 1080,
      close: vi.fn(),
    } as unknown as ImageBitmap;

    globalThis.createImageBitmap = vi.fn().mockResolvedValue(mockBitmap);

    const compressedBlob = new Blob([new Uint8Array(500 * 1024)], { type: 'image/webp' });
    class MockOffscreenCanvas {
      constructor(
        public width: number,
        public height: number,
      ) {}
      getContext() {
        return { drawImage: vi.fn() };
      }
      convertToBlob = vi.fn().mockResolvedValue(compressedBlob);
    }
    globalThis.OffscreenCanvas = MockOffscreenCanvas as unknown as typeof OffscreenCanvas;

    const result = await admitAndCompressImageFile(heavyFile);
    expect(result.name).toBe('render.webp');
    expect(result.size).toBe(500 * 1024);
  });

  it('falls back to original file gracefully if bitmap decoding throws an exception', async () => {
    const corruptFile = new File(['bad image data'], 'broken.png', { type: 'image/png' });
    globalThis.createImageBitmap = vi.fn().mockRejectedValue(new Error('Corrupt image payload'));

    const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const result = await admitAndCompressImageFile(corruptFile);

    expect(result).toBe(corruptFile);
    expect(consoleWarnSpy).toHaveBeenCalled();
  });

  it('processes batch of files preserving order and non-image files via admitAndCompressFiles', async () => {
    const textFile = new File(['text'], 'doc.txt', { type: 'text/plain' });
    const smallPng = new File([new Uint8Array(100)], 'small.png', { type: 'image/png' });
    const mockBitmap = { width: 500, height: 500, close: vi.fn() } as unknown as ImageBitmap;
    globalThis.createImageBitmap = vi.fn().mockResolvedValue(mockBitmap);

    const results = await admitAndCompressFiles([textFile, smallPng]);
    expect(results).toHaveLength(2);
    expect(results[0]).toBe(textFile);
    expect(results[1]).toBe(smallPng);
  });
});
