import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/store/useProviderStore', () => ({
  default: {
    getState: () => ({
      defaultModelConfig: {
        baseModel: {
          primary: { providerId: 'openai', model: 'gpt-4o' },
        },
      },
      getModelInfo: () => ({ supports_vision: true }),
    }),
  },
}));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => false,
}));

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

  it('injects camera frames as image_url parts', async () => {
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

describe('buildMultimodalQuery - model vision support', () => {
  it('ignores camera frames when model does not support vision', async () => {
    const storeModule = await import('@/store/useProviderStore');
    const originalGetState = storeModule.default.getState;

    storeModule.default.getState = () => {
      const originalState = originalGetState();
      return {
        ...originalState,
        defaultModelConfig: {
          ...originalState.defaultModelConfig,
          baseModel: {
            ...originalState.defaultModelConfig.baseModel,
            primary: { providerId: 'openai', model: 'gpt-3.5' },
          },
        },
        getModelInfo: () => ({ source: 'user', lastUpdated: new Date().toISOString(), supports_vision: false }),
      };
    };

    try {
      const frames = ['data:image/jpeg;base64,abc123'];
      const result = await buildMultimodalQuery('hello', [], frames);
      expect(result).toBe('hello');
    } finally {
      storeModule.default.getState = originalGetState;
    }
  });
});
