import { beforeEach, describe, expect, it, vi } from 'vitest';

const isTauriRuntime = vi.hoisted(() => vi.fn(() => false));

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return { ...actual, isTauriRuntime };
});
vi.mock('@/services/file-service/types', () => ({ fromStoreFile: (f: unknown) => f }));
vi.mock('@/services/file', () => ({ extractPdfContent: vi.fn() }));
vi.mock('@/services/i18nToastService', () => ({ showI18nToast: vi.fn() }));
vi.mock('@/store/useConfigStore', () => ({ default: { getState: () => ({ extractDocumentText: true }) } }));

import type { File } from '@/store/chat/types';
import { buildMultimodalQuery, type VisionContentPart } from '@/store/chat/multimodalBuilder';

function generatedImage(mediaId: string, extra: Partial<File> = {}): File {
  return {
    fileName: `${mediaId}.png`,
    fileExtension: 'png',
    fileUrl: `http://127.0.0.1:8080/api/v1/media/${mediaId}/file`,
    fileType: 'uploaded',
    status: 'ready',
    mediaId,
    ...extra,
  };
}

async function build(files: File[]): Promise<VisionContentPart[]> {
  return (await buildMultimodalQuery('make it watercolor', files)) as VisionContentPart[];
}

describe('buildMultimodalQuery: images taken from the media library', () => {
  beforeEach(() => {
    isTauriRuntime.mockReturnValue(false);
  });

  it('sends the image by its media address and names that address in a text handle', async () => {
    const parts = await build([generatedImage('media_abc')]);

    expect(parts).toEqual([
      { type: 'text', text: 'make it watercolor' },
      { type: 'image_url', image_url: { url: 'media://media_abc', detail: 'auto' } },
      { type: 'text', text: '[Attachment: media_abc.png → media://media_abc]' },
    ]);
  });

  it.each([true, false])(
    'addresses it the same way whether the app is the desktop shell (%s) or not',
    async (tauri) => {
      isTauriRuntime.mockReturnValue(tauri);

      const parts = await build([generatedImage('media_abc')]);

      expect(parts[1]).toEqual({ type: 'image_url', image_url: { url: 'media://media_abc', detail: 'auto' } });
    },
  );

  it('gives each of several images its own handle right after its image block', async () => {
    const parts = await build([generatedImage('media_one'), generatedImage('media_two')]);

    expect(parts.slice(1)).toEqual([
      { type: 'image_url', image_url: { url: 'media://media_one', detail: 'auto' } },
      { type: 'text', text: '[Attachment: media_one.png → media://media_one]' },
      { type: 'image_url', image_url: { url: 'media://media_two', detail: 'auto' } },
      { type: 'text', text: '[Attachment: media_two.png → media://media_two]' },
    ]);
  });

  it('leaves a plain uploaded image as it was: its URL, and no handle', async () => {
    const upload: File = {
      id: 'img1',
      fileName: 'photo.png',
      fileExtension: 'png',
      fileUrl: '/api/media/files/img1/content',
      fileType: 'uploaded',
    };

    const parts = await build([upload]);

    expect(parts).toEqual([
      { type: 'text', text: 'make it watercolor' },
      { type: 'image_url', image_url: { url: '/api/media/files/img1/content', detail: 'auto' } },
    ]);
  });

  it('keeps the order of mixed attachments and gives only the media-library one a handle', async () => {
    const upload: File = {
      id: 'img1',
      fileName: 'photo.png',
      fileExtension: 'png',
      fileUrl: '/api/media/files/img1/content',
      fileType: 'uploaded',
    };

    const parts = await build([upload, generatedImage('media_abc')]);

    expect(parts.map((part) => part.type)).toEqual(['text', 'image_url', 'image_url', 'text']);
    expect(parts[3]).toEqual({ type: 'text', text: '[Attachment: media_abc.png → media://media_abc]' });
  });
});
