import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return {
    ...actual,
    isTauriRuntime: vi.fn(() => false),
  };
});

vi.mock('@/services/file-service/types', () => ({
  fromStoreFile: (f: unknown) => f,
}));

vi.mock('@/services/file', () => ({
  extractPdfContent: vi.fn(),
}));

vi.mock('@/lib/utils/fileUtils', () => ({
  partitionFilesByType: (files: { fileExtension: string }[]) => ({
    imageFiles: files.filter((f) => ['jpg', 'png'].includes(f.fileExtension)),
    videoFiles: [],
    pdfFiles: files.filter((f) => f.fileExtension === 'pdf'),
    documentFiles: [],
    textFiles: [],
    otherFiles: [],
  }),
  getMimeType: (ext: string) => `image/${ext}`,
}));

vi.mock('@/store/useConfigStore', () => ({
  default: {
    getState: () => ({ extractDocumentText: true }),
  },
}));

import { buildMultimodalQuery, type VisionContentPart } from '@/store/chat/multimodalBuilder';

describe('buildMultimodalQuery with cameraFrames', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns plain text when no files and no camera frames', async () => {
    const result = await buildMultimodalQuery('hello', []);
    expect(result).toBe('hello');
  });

  it('returns plain text when camera frames empty', async () => {
    const result = await buildMultimodalQuery('hello', [], []);
    expect(result).toBe('hello');
  });

  it('injects camera frames as image_url parts regardless of model vision support', async () => {
    const frames = ['data:image/jpeg;base64,abc123'];
    const result = await buildMultimodalQuery('describe this', [], frames);

    expect(typeof result).not.toBe('string');
    const parts = result as VisionContentPart[];
    expect(parts).toHaveLength(2);
    expect(parts[0]).toEqual({ type: 'text', text: 'describe this' });
    expect(parts[1]).toEqual({
      type: 'image_url',
      image_url: { url: 'data:image/jpeg;base64,abc123', detail: 'auto' },
    });
  });

  it('injects multiple camera frames', async () => {
    const frames = ['data:image/jpeg;base64,frame1', 'data:image/jpeg;base64,frame2', 'data:image/jpeg;base64,frame3'];
    const result = await buildMultimodalQuery('what is this', [], frames);

    const parts = result as VisionContentPart[];
    expect(parts).toHaveLength(4);
    expect(parts[0].type).toBe('text');
    expect(parts[1].type).toBe('image_url');
    expect(parts[2].type).toBe('image_url');
    expect(parts[3].type).toBe('image_url');
  });
});

describe('buildMultimodalQuery - undefined cameraFrames', () => {
  it('returns plain text when cameraFrames is explicitly undefined', async () => {
    const result = await buildMultimodalQuery('hello world', [], undefined);
    expect(result).toBe('hello world');
  });
});

describe('buildMultimodalQuery - vision-agnostic behavior', () => {
  it('always sends camera frames to backend for VisionFallbackEngine routing', async () => {
    const frames = ['data:image/jpeg;base64,abc123'];
    const result = await buildMultimodalQuery('hello', [], frames);

    expect(typeof result).not.toBe('string');
    const parts = result as VisionContentPart[];
    expect(parts).toHaveLength(2);
    expect(parts[1]).toEqual({
      type: 'image_url',
      image_url: { url: 'data:image/jpeg;base64,abc123', detail: 'auto' },
    });
  });
});

describe('buildMultimodalQuery - image URL referencing (Sandbox mode)', () => {
  it('passes fileUrl directly instead of converting to base64', async () => {
    const imageFile = {
      id: 'img1',
      fileName: 'photo.jpg',
      fileExtension: 'jpg',
      fileUrl: '/api/media/files/img1/content',
    };
    const result = await buildMultimodalQuery('describe this', [imageFile] as any);

    expect(typeof result).not.toBe('string');
    const parts = result as VisionContentPart[];
    const imageParts = parts.filter((p) => p.type === 'image_url');
    expect(imageParts).toHaveLength(1);
    expect(imageParts[0]).toEqual({
      type: 'image_url',
      image_url: { url: '/api/media/files/img1/content', detail: 'auto' },
    });
  });

  it('skips images with no fileUrl', async () => {
    const imageFile = { id: 'img2', fileName: 'broken.png', fileExtension: 'png', fileUrl: '' };
    const result = await buildMultimodalQuery('test', [imageFile] as any);
    expect(result).toBe('test');
  });
});

describe('buildMultimodalQuery - Tauri mode uses file:// path', () => {
  it('returns file:// URL for images with localPath in Tauri mode', async () => {
    const { isTauriRuntime } = await import('@/lib/deploy-mode');
    vi.mocked(isTauriRuntime).mockReturnValue(true);

    const imageFile = {
      id: 'img-tauri',
      fileName: 'local-photo.jpg',
      fileExtension: 'jpg',
      localPath: '/Users/test/Pictures/local-photo.jpg',
    };
    const result = await buildMultimodalQuery('describe this', [imageFile] as any);

    expect(typeof result).not.toBe('string');
    const parts = result as VisionContentPart[];
    const imageParts = parts.filter((p) => p.type === 'image_url');
    expect(imageParts).toHaveLength(1);
    expect(imageParts[0]).toEqual({
      type: 'image_url',
      image_url: { url: 'file:///Users/test/Pictures/local-photo.jpg', detail: 'auto' },
    });

    vi.mocked(isTauriRuntime).mockReturnValue(false);
  });

  it('returns null for Tauri images without localPath', async () => {
    const { isTauriRuntime } = await import('@/lib/deploy-mode');
    vi.mocked(isTauriRuntime).mockReturnValue(true);

    const imageFile = { id: 'img-no-path', fileName: 'broken.png', fileExtension: 'png' };
    const result = await buildMultimodalQuery('test', [imageFile] as any);
    expect(result).toBe('test');

    vi.mocked(isTauriRuntime).mockReturnValue(false);
  });
});

describe('buildMultimodalQuery - PDF images always included', () => {
  it('includes PDF images regardless of primary model vision capability', async () => {
    const { extractPdfContent } = await import('@/services/file');
    const mockExtract = vi.mocked(extractPdfContent);
    mockExtract.mockResolvedValue({
      text: 'Chart data summary',
      images: [{ mimeType: 'image/png', data: 'base64chart' }],
      imageTrace: { keptCount: 1, droppedCount: 2 },
    });

    const pdfFile = { id: 'f1', fileName: 'report.pdf', fileExtension: 'pdf', fileUrl: '/files/f1' };
    const result = await buildMultimodalQuery('analyze this', [pdfFile] as any);

    const parts = result as VisionContentPart[];
    const imageParts = parts.filter((p) => p.type === 'image_url');
    expect(imageParts).toHaveLength(1);
    expect(imageParts[0]).toEqual({
      type: 'image_url',
      image_url: { url: 'data:image/png;base64,base64chart', detail: 'auto' },
    });
  });

  it('prefers fileUrl from PDF extraction when available', async () => {
    const { extractPdfContent } = await import('@/services/file');
    const mockExtract = vi.mocked(extractPdfContent);
    mockExtract.mockResolvedValue({
      text: '',
      images: [{ mimeType: 'image/png', data: '', fileUrl: '/api/media/files/pdf-img-1/content' }],
      imageTrace: { keptCount: 1, droppedCount: 0 },
    });

    const pdfFile = { id: 'f2', fileName: 'charts.pdf', fileExtension: 'pdf', fileUrl: '/files/f2' };
    const result = await buildMultimodalQuery('analyze', [pdfFile] as any);

    const parts = result as VisionContentPart[];
    const imageParts = parts.filter((p) => p.type === 'image_url');
    expect(imageParts).toHaveLength(1);
    expect(imageParts[0]).toEqual({
      type: 'image_url',
      image_url: { url: '/api/media/files/pdf-img-1/content', detail: 'auto' },
    });
  });
});
