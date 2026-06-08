import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return {
    ...actual,
    isTauriRuntime: () => false,
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
  fetchFileAsBase64DataURL: vi.fn(),
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
});
