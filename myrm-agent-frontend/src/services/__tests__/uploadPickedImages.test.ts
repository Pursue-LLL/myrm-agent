import { beforeEach, describe, expect, it, vi } from 'vitest';

const uploadFiles = vi.hoisted(() => vi.fn());
const admitAndCompressFiles = vi.hoisted(() => vi.fn());

vi.mock('@/services/file', () => ({ uploadFiles }));
vi.mock('@/lib/utils/imageAdmission', () => ({ admitAndCompressFiles }));

import type { FileReference } from '@/services/file-service';
import { uploadPickedImages } from '@/services/file-service/uploadPickedImages';

const local = (fileName: string): FileReference => ({
  fileName,
  fileExtension: fileName.split('.').pop() ?? '',
  fileType: 'local_path',
  localPath: `/home/me/${fileName}`,
});

const readBytes = vi.fn(async (ref: FileReference) => new TextEncoder().encode(`bytes of ${ref.fileName}`));

function serverKeeps(names: string[]) {
  uploadFiles.mockImplementation(async (files: File[]) => ({
    uploaded_count: files.length,
    files: names.map((name) => ({ fileId: `id:${name}`, fileName: name, fileUrl: `/uploads/${name}` })),
  }));
}

describe('uploadPickedImages', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    admitAndCompressFiles.mockImplementation(async (files: File[]) => files);
  });

  it('returns the very same list, without reading or uploading anything, when there is no local image', async () => {
    const refs = [local('a.pdf'), { ...local('b.png'), localPath: undefined, fileType: 'uploaded' as const }];

    const result = await uploadPickedImages(refs, readBytes);

    expect(result).toBe(refs);
    expect(readBytes).not.toHaveBeenCalled();
    expect(uploadFiles).not.toHaveBeenCalled();
  });

  it('uploads exactly the local images, in order, and puts the server id and URL next to the local path', async () => {
    serverKeeps(['one.png', 'two.jpg']);
    const refs = [local('one.png'), local('notes.pdf'), local('two.jpg')];

    const result = await uploadPickedImages(
      refs,
      readBytes,
      { incognitoChatId: 'chat-1' },
      new AbortController().signal,
    );

    const [uploadedFiles, signal, options] = uploadFiles.mock.calls[0];
    expect((uploadedFiles as File[]).map((file) => [file.name, file.type])).toEqual([
      ['one.png', 'image/png'],
      ['two.jpg', 'image/jpeg'],
    ]);
    expect(await (uploadedFiles as File[])[0].text()).toBe('bytes of one.png');
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(options).toEqual({ incognitoChatId: 'chat-1' });
    expect(result).toEqual([
      { ...local('one.png'), id: 'id:one.png', fileUrl: '/uploads/one.png' },
      local('notes.pdf'),
      { ...local('two.jpg'), id: 'id:two.jpg', fileUrl: '/uploads/two.jpg' },
    ]);
  });

  it('uploads what the admission step made of the images, not the originals', async () => {
    serverKeeps(['small.webp']);
    admitAndCompressFiles.mockImplementation(async () => [new File(['tiny'], 'small.webp', { type: 'image/webp' })]);

    const result = await uploadPickedImages([local('huge.png')], readBytes);

    expect((uploadFiles.mock.calls[0][0] as File[]).map((file) => file.name)).toEqual(['small.webp']);
    expect(result[0]).toEqual({ ...local('huge.png'), id: 'id:small.webp', fileUrl: '/uploads/small.webp' });
  });

  it('fails, naming the counts, when the server kept fewer images than were sent', async () => {
    serverKeeps(['one.png']);

    await expect(uploadPickedImages([local('one.png'), local('two.png')], readBytes)).rejects.toThrow(
      'The server kept 1 of 2 images',
    );
  });

  it('lets a failed read or a failed upload reach the caller', async () => {
    readBytes.mockRejectedValueOnce(new Error('cannot read'));
    await expect(uploadPickedImages([local('one.png')], readBytes)).rejects.toThrow('cannot read');

    uploadFiles.mockRejectedValueOnce(new Error('HTTP 413'));
    await expect(uploadPickedImages([local('one.png')], readBytes)).rejects.toThrow('HTTP 413');
  });
});
