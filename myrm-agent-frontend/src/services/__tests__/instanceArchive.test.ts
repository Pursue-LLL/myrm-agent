import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ apiRequest: vi.fn(), fetchWithTimeout: vi.fn() }));
const desktop = vi.hoisted(() => ({ active: false, save: vi.fn(), writeFile: vi.fn() }));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: api.apiRequest,
  fetchWithTimeout: api.fetchWithTimeout,
}));
vi.mock('@/lib/deploy-mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/deploy-mode')>()),
  isTauriRuntime: () => desktop.active,
}));
vi.mock('@tauri-apps/plugin-dialog', () => ({ save: desktop.save }));
vi.mock('@tauri-apps/plugin-fs', () => ({ writeFile: desktop.writeFile }));

import { ApiError } from '@/lib/api';
import { archiveErrorCode, instanceArchiveService, UPLOAD_CHUNK_BYTES } from '../instanceArchive';

const session = (overrides: Record<string, unknown> = {}) => ({
  session_id: 's1',
  size_bytes: UPLOAD_CHUNK_BYTES * 2 + 10,
  chunk_bytes: UPLOAD_CHUNK_BYTES,
  chunk_count: 3,
  received: [] as number[],
  state: 'uploading',
  ...overrides,
});

const fileOf = (size: number) => new File([new Uint8Array(size)], 'backup.zip', { lastModified: 1 });

const zipResponse = () => {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('PK'));
        controller.enqueue(encoder.encode('zip'));
        controller.close();
      },
    }),
    { status: 200 },
  );
};

describe('instanceArchiveService', () => {
  beforeEach(() => {
    api.apiRequest.mockReset();
    api.fetchWithTimeout.mockReset();
    desktop.active = false;
    desktop.save.mockReset();
    desktop.writeFile.mockReset();
    Reflect.deleteProperty(window, 'showSaveFilePicker');
    window.localStorage.clear();
    vi.useRealTimers();
  });

  it('uploads sequential chunks with raw bytes and reports progress', async () => {
    api.apiRequest.mockImplementation(async (path: string, options: RequestInit) => {
      if (path === '/instance-archive/imports') {
        return session();
      }
      return session({ received: [Number(path.split('/').pop())] });
    });
    const progress: number[] = [];

    const result = await instanceArchiveService.uploadArchive(fileOf(UPLOAD_CHUNK_BYTES * 2 + 10), {
      onProgress: (p) => progress.push(p.chunksDone),
    });

    expect(result.session_id).toBe('s1');
    expect(progress).toEqual([0, 1, 2, 3]);
    const puts = api.apiRequest.mock.calls.filter(([, options]) => options?.method === 'PUT');
    expect(puts.map(([path]) => path)).toEqual([
      '/instance-archive/imports/s1/chunks/0',
      '/instance-archive/imports/s1/chunks/1',
      '/instance-archive/imports/s1/chunks/2',
    ]);
    expect(puts[0][1].headers).toEqual({ 'Content-Type': 'application/octet-stream' });
    expect((puts[2][1].body as Blob).size).toBe(10);
  });

  it('resumes the same file in its existing session and skips received chunks', async () => {
    window.localStorage.setItem(
      'myrm.instanceArchive.upload',
      JSON.stringify({ fileKey: `backup.zip:${UPLOAD_CHUNK_BYTES * 2 + 10}:1`, sessionId: 's1' }),
    );
    api.apiRequest.mockImplementation(async (path: string, options: RequestInit) => {
      if (options?.method === 'PUT') {
        return session({ received: [0, 1, 2] });
      }
      return session({ received: [0, 1] });
    });

    await instanceArchiveService.uploadArchive(fileOf(UPLOAD_CHUNK_BYTES * 2 + 10));

    const puts = api.apiRequest.mock.calls.filter(([, options]) => options?.method === 'PUT');
    expect(puts.map(([path]) => path)).toEqual(['/instance-archive/imports/s1/chunks/2']);
    expect(api.apiRequest.mock.calls.some(([path]) => path === '/instance-archive/imports')).toBe(false);
  });

  it('retries transport failures but treats 4xx answers as final', async () => {
    vi.useFakeTimers();
    let attempts = 0;
    api.apiRequest.mockImplementation(async (path: string, options: RequestInit) => {
      if (options?.method !== 'PUT') {
        return session({ chunk_count: 1, size_bytes: 5 });
      }
      attempts += 1;
      if (attempts < 3) {
        throw new TypeError('network');
      }
      return session({ chunk_count: 1, size_bytes: 5, received: [0] });
    });
    const pending = instanceArchiveService.uploadArchive(fileOf(5));
    await vi.advanceTimersByTimeAsync(10_000);
    await pending;
    expect(attempts).toBe(3);

    vi.useRealTimers();
    attempts = 0;
    window.localStorage.clear();
    api.apiRequest.mockImplementation(async (_path: string, options: RequestInit) => {
      if (options?.method !== 'PUT') {
        return session({ chunk_count: 1, size_bytes: 5 });
      }
      attempts += 1;
      throw new ApiError('no space', 507, [], undefined, 'insufficient_space');
    });
    await expect(instanceArchiveService.uploadArchive(fileOf(5))).rejects.toMatchObject({
      businessCode: 'insufficient_space',
    });
    expect(attempts).toBe(1);
  });

  it('turns the envelope into a nullable outcome', async () => {
    api.apiRequest.mockResolvedValueOnce({ outcome: null }).mockResolvedValueOnce({});
    expect(await instanceArchiveService.getOutcome()).toBeNull();
    expect(await instanceArchiveService.getOutcome()).toBeNull();
    api.apiRequest.mockResolvedValueOnce({ outcome: { status: 'restored' } });
    expect(await instanceArchiveService.getOutcome()).toEqual({ status: 'restored' });
  });

  it('downloads through a blob when the browser cannot stream to disk', async () => {
    api.fetchWithTimeout.mockResolvedValue(zipResponse());
    const createObjectURL = vi.fn(() => 'blob:x');
    Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() });
    const clicks = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const received: number[] = [];

    const outcome = await instanceArchiveService.downloadExport('job1', (n) => received.push(n));

    expect(outcome).toBe('saved');
    expect(received).toEqual([2, 5]);
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(clicks).toHaveBeenCalledOnce();
    expect(api.fetchWithTimeout.mock.calls[0][0]).toBe('/instance-archive/exports/job1/download');
    expect(api.fetchWithTimeout.mock.calls[0][2]).toBe(0);
  });

  it('saves through the native dialog on the desktop shell even when the webview offers a file picker', async () => {
    desktop.active = true;
    desktop.save.mockResolvedValue('/Users/me/backup.zip');
    const picker = vi.fn();
    Object.assign(window, { showSaveFilePicker: picker });
    api.fetchWithTimeout.mockResolvedValue(zipResponse());

    const outcome = await instanceArchiveService.downloadExport('job1');

    expect(outcome).toBe('saved');
    expect(picker).not.toHaveBeenCalled();
    expect(desktop.writeFile).toHaveBeenCalledWith('/Users/me/backup.zip', expect.any(Uint8Array));
  });

  it('reports a cancelled native save dialog so the finished backup stays available', async () => {
    desktop.active = true;
    desktop.save.mockResolvedValue(null);
    api.fetchWithTimeout.mockResolvedValue(zipResponse());

    await expect(instanceArchiveService.downloadExport('job1')).resolves.toBe('cancelled');
    expect(desktop.writeFile).not.toHaveBeenCalled();
  });

  it('surfaces the stable code of a refused download', async () => {
    api.fetchWithTimeout.mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: 'export_not_ready' } }), { status: 409 }),
    );
    await expect(instanceArchiveService.downloadExport('job1')).rejects.toMatchObject({
      businessCode: 'export_not_ready',
    });
  });
});

describe('archiveErrorCode', () => {
  it('reads the business code and falls back to generic', () => {
    expect(archiveErrorCode(new ApiError('x', 409, [], undefined, 'operation_pending'))).toBe('operation_pending');
    expect(archiveErrorCode(new Error('boom'))).toBe('generic');
  });
});
