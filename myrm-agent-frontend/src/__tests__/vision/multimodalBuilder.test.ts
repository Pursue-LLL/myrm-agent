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

vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: vi.fn(),
}));

import { showI18nToast } from '@/services/i18nToastService';
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
      fileType: 'uploaded' as const,
    };
    const result = await buildMultimodalQuery('describe this', [imageFile]);

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
    const imageFile = {
      id: 'img2',
      fileName: 'broken.png',
      fileExtension: 'png',
      fileUrl: '',
      fileType: 'uploaded' as const,
    };
    const result = await buildMultimodalQuery('test', [imageFile]);
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
      fileType: 'local_path' as const,
    };
    const result = await buildMultimodalQuery('describe this', [imageFile]);

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

    const imageFile = {
      id: 'img-no-path',
      fileName: 'broken.png',
      fileExtension: 'png',
      fileType: 'uploaded' as const,
    };
    const result = await buildMultimodalQuery('test', [imageFile]);
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
      pageCount: 1,
      parsedPages: 1,
      strategy: 'hybrid',
      tables: [],
      imageTrace: { totalProcessed: 3, keptCount: 1, droppedCount: 2, dropReasons: {} },
    });

    const pdfFile = {
      id: 'f1',
      fileName: 'report.pdf',
      fileExtension: 'pdf',
      fileUrl: '/files/f1',
      fileType: 'uploaded' as const,
    };
    const result = await buildMultimodalQuery('analyze this', [pdfFile]);

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
      pageCount: 1,
      parsedPages: 1,
      strategy: 'hybrid',
      tables: [],
      imageTrace: { totalProcessed: 1, keptCount: 1, droppedCount: 0, dropReasons: {} },
    });

    const pdfFile = {
      id: 'f2',
      fileName: 'charts.pdf',
      fileExtension: 'pdf',
      fileUrl: '/files/f2',
      fileType: 'uploaded' as const,
    };
    const result = await buildMultimodalQuery('analyze', [pdfFile]);

    const parts = result as VisionContentPart[];
    const imageParts = parts.filter((p) => p.type === 'image_url');
    expect(imageParts).toHaveLength(1);
    expect(imageParts[0]).toEqual({
      type: 'image_url',
      image_url: { url: '/api/media/files/pdf-img-1/content', detail: 'auto' },
    });
  });
});

describe('buildMultimodalQuery - PDF without readable content', () => {
  const blankPdf = {
    id: 'f4',
    fileName: 'blank.pdf',
    fileExtension: 'pdf',
    fileUrl: '/files/f4',
    fileType: 'uploaded' as const,
  };

  it('keeps the attachment visible to the model when extraction returns neither text nor images', async () => {
    const { extractPdfContent } = await import('@/services/file');
    vi.mocked(extractPdfContent).mockResolvedValue({
      text: '',
      images: [],
      pageCount: 3,
      parsedPages: 3,
      strategy: 'image',
      tables: [],
    });

    const result = await buildMultimodalQuery('summarize', [blankPdf]);

    expect(result).toEqual([
      { type: 'text', text: 'summarize' },
      { type: 'text', text: '[Attachment: blank.pdf]' },
    ]);
  });

  it('adds no reference when page images carry the content', async () => {
    const { extractPdfContent } = await import('@/services/file');
    vi.mocked(extractPdfContent).mockResolvedValue({
      text: '',
      images: [{ mimeType: 'image/png', data: 'scan' }],
      pageCount: 1,
      parsedPages: 1,
      strategy: 'image',
      tables: [],
    });

    const result = (await buildMultimodalQuery('read it', [blankPdf])) as VisionContentPart[];

    expect(result.filter((part) => part.type === 'text' && part.text.startsWith('[Attachment'))).toHaveLength(0);
    expect(result.filter((part) => part.type === 'image_url')).toHaveLength(1);
  });
});

describe('buildMultimodalQuery - PDF extraction notices', () => {
  const pdfFile = {
    id: 'f3',
    fileName: 'big.pdf',
    fileExtension: 'pdf',
    fileUrl: '/files/f3',
    fileType: 'uploaded' as const,
  };

  beforeEach(() => {
    vi.mocked(showI18nToast).mockClear();
  });

  it('tells the user how many pages were parsed when the PDF was only partially read', async () => {
    const { extractPdfContent } = await import('@/services/file');
    vi.mocked(extractPdfContent).mockResolvedValue({
      text: 'First pages',
      images: [],
      pageCount: 5,
      parsedPages: 2,
      strategy: 'text',
      tables: [],
    });

    await buildMultimodalQuery('summarize', [pdfFile]);

    expect(showI18nToast).toHaveBeenCalledTimes(1);
    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.pdfParsedPages',
      { fileName: 'big.pdf', parsed: 2, total: 5 },
      { type: 'info', duration: 5000 },
    );
  });

  it('reports the real kept and dropped image counts without an invented time saving', async () => {
    const { extractPdfContent } = await import('@/services/file');
    vi.mocked(extractPdfContent).mockResolvedValue({
      text: '',
      images: [{ mimeType: 'image/png', data: 'base64chart' }],
      pageCount: 1,
      parsedPages: 1,
      strategy: 'hybrid',
      tables: [],
      imageTrace: { totalProcessed: 3, keptCount: 1, droppedCount: 2, dropReasons: {} },
    });

    await buildMultimodalQuery('analyze', [pdfFile]);

    expect(showI18nToast).toHaveBeenCalledTimes(1);
    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.pdfImageOptimized',
      { kept: 1, dropped: 2 },
      { type: 'success', duration: 6000 },
    );
  });

  it('stays quiet when every page was parsed and no image was filtered out', async () => {
    const { extractPdfContent } = await import('@/services/file');
    vi.mocked(extractPdfContent).mockResolvedValue({
      text: 'All pages',
      images: [{ mimeType: 'image/png', data: 'base64chart' }],
      pageCount: 1,
      parsedPages: 1,
      strategy: 'hybrid',
      tables: [],
      imageTrace: { totalProcessed: 1, keptCount: 1, droppedCount: 0, dropReasons: {} },
    });

    await buildMultimodalQuery('analyze', [pdfFile]);

    expect(showI18nToast).not.toHaveBeenCalled();
  });

  it('says figures were withheld when the delivery window cut the scan short', async () => {
    const { extractPdfContent } = await import('@/services/file');
    vi.mocked(extractPdfContent).mockResolvedValue({
      text: 'Chapters',
      images: [{ mimeType: 'image/png', data: 'base64chart' }],
      pageCount: 40,
      parsedPages: 40,
      strategy: 'hybrid',
      tables: [],
      imageTrace: {
        totalProcessed: 30,
        keptCount: 30,
        droppedCount: 0,
        dropReasons: {},
        truncated: true,
      },
    });

    await buildMultimodalQuery('analyze', [pdfFile]);

    expect(showI18nToast).toHaveBeenCalledTimes(1);
    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.pdfFiguresTruncated',
      { kept: 30 },
      { type: 'info', duration: 6000 },
    );
  });

  it('names the scanned pages when the text layer could not read them', async () => {
    const { extractPdfContent } = await import('@/services/file');
    vi.mocked(extractPdfContent).mockResolvedValue({
      text: 'Contract body',
      images: [
        { mimeType: 'image/png', data: 'p4', pageNumber: 4 },
        { mimeType: 'image/png', data: 'p5', pageNumber: 5 },
      ],
      pageCount: 6,
      parsedPages: 6,
      pagesWithoutText: [4, 5],
      strategy: 'hybrid',
      tables: [],
    });

    await buildMultimodalQuery('summarize', [pdfFile]);

    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.pdfScannedPages',
      { fileName: 'big.pdf', pages: '4-5' },
      { type: 'info', duration: 6000 },
    );
  });

  it('collapses the scanned page list into ranges', async () => {
    const { extractPdfContent } = await import('@/services/file');
    vi.mocked(extractPdfContent).mockResolvedValue({
      text: 'Contract body',
      images: [
        { mimeType: 'image/png', data: 'p2', pageNumber: 2 },
        { mimeType: 'image/png', data: 'p3', pageNumber: 3 },
        { mimeType: 'image/png', data: 'p4', pageNumber: 4 },
        { mimeType: 'image/png', data: 'p8', pageNumber: 8 },
      ],
      pageCount: 10,
      parsedPages: 10,
      pagesWithoutText: [2, 3, 4, 8],
      strategy: 'hybrid',
      tables: [],
    });

    await buildMultimodalQuery('summarize', [pdfFile]);

    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.pdfScannedPages',
      { fileName: 'big.pdf', pages: '2-4, 8' },
      { type: 'info', duration: 6000 },
    );
  });

  it('warns instead of claiming delivery when scanned pages exceed the image ceiling', async () => {
    /**
     * Past the per-delivery image ceiling the scan pages are dropped, so the copy must not
     * say they were "sent as images" — that would promise content the model never received.
     */
    const { extractPdfContent } = await import('@/services/file');
    vi.mocked(extractPdfContent).mockResolvedValue({
      text: 'Contract body',
      images: [{ mimeType: 'image/png', data: 'p4', pageNumber: 4 }],
      pageCount: 10,
      parsedPages: 10,
      pagesWithoutText: [4, 5, 6],
      strategy: 'hybrid',
      tables: [],
    });

    await buildMultimodalQuery('summarize', [pdfFile]);

    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.pdfScannedPages',
      { fileName: 'big.pdf', pages: '4' },
      { type: 'info', duration: 6000 },
    );
    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.pdfScannedPagesWithheld',
      { fileName: 'big.pdf', pages: '5-6' },
      { type: 'warning', duration: 8000 },
    );
  });

  it('stays quiet about scanned pages when the text layer read every page', async () => {
    const { extractPdfContent } = await import('@/services/file');
    vi.mocked(extractPdfContent).mockResolvedValue({
      text: 'All readable',
      images: [],
      pageCount: 3,
      parsedPages: 3,
      pagesWithoutText: [],
      strategy: 'text',
      tables: [],
    });

    await buildMultimodalQuery('summarize', [pdfFile]);

    expect(showI18nToast).not.toHaveBeenCalled();
  });

  it('prefers the truncation notice over the ablation summary when both would apply', async () => {
    const { extractPdfContent } = await import('@/services/file');
    vi.mocked(extractPdfContent).mockResolvedValue({
      text: 'Chapters',
      images: [{ mimeType: 'image/png', data: 'base64chart' }],
      pageCount: 40,
      parsedPages: 40,
      strategy: 'hybrid',
      tables: [],
      imageTrace: {
        totalProcessed: 30,
        keptCount: 28,
        droppedCount: 2,
        dropReasons: { monochrome_or_blank: 2 },
        truncated: true,
      },
    });

    await buildMultimodalQuery('analyze', [pdfFile]);

    expect(showI18nToast).toHaveBeenCalledTimes(1);
    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.pdfFiguresTruncated',
      { kept: 28 },
      { type: 'info', duration: 6000 },
    );
  });
});
