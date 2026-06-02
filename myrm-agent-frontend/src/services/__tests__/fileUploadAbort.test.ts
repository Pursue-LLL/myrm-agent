import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { uploadFilesWithProgress } from '../file';

interface MockXHR {
  open: ReturnType<typeof vi.fn>;
  send: ReturnType<typeof vi.fn>;
  abort: ReturnType<typeof vi.fn>;
  setRequestHeader: ReturnType<typeof vi.fn>;
  status: number;
  responseText: string;
  upload: { onprogress: ((e: ProgressEvent) => void) | null };
  onload: (() => void) | null;
  onerror: (() => void) | null;
}

function createMockXHR(): MockXHR {
  return {
    open: vi.fn(),
    send: vi.fn(),
    abort: vi.fn(),
    setRequestHeader: vi.fn(),
    status: 200,
    responseText: '',
    upload: { onprogress: null },
    onload: null,
    onerror: null,
  };
}

describe('uploadFilesWithProgress signal handling', () => {
  let mockXHR: MockXHR;
  let originalXHR: typeof XMLHttpRequest;

  beforeEach(() => {
    mockXHR = createMockXHR();
    originalXHR = globalThis.XMLHttpRequest;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    globalThis.XMLHttpRequest = function () {
      return mockXHR;
    } as any;
  });

  afterEach(() => {
    globalThis.XMLHttpRequest = originalXHR;
  });

  it('rejects immediately if signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();

    const file = new File(['content'], 'test.txt', { type: 'text/plain' });
    const onProgress = vi.fn();

    await expect(uploadFilesWithProgress([file], onProgress, controller.signal)).rejects.toThrow('Upload aborted');

    expect(mockXHR.open).not.toHaveBeenCalled();
    expect(mockXHR.send).not.toHaveBeenCalled();
  });

  it('aborts XHR when signal fires during upload', async () => {
    const controller = new AbortController();
    const file = new File(['content'], 'test.txt', { type: 'text/plain' });
    const onProgress = vi.fn();

    const uploadPromise = uploadFilesWithProgress([file], onProgress, controller.signal);

    expect(mockXHR.open).toHaveBeenCalledWith('POST', expect.stringContaining('/files/upload'));
    expect(mockXHR.send).toHaveBeenCalled();

    controller.abort();

    await expect(uploadPromise).rejects.toThrow('Upload aborted');
    expect(mockXHR.abort).toHaveBeenCalled();
  });

  it('rejects with AbortError name for proper error handling', async () => {
    const controller = new AbortController();
    const file = new File(['content'], 'test.txt', { type: 'text/plain' });

    const uploadPromise = uploadFilesWithProgress([file], vi.fn(), controller.signal);
    controller.abort();

    try {
      await uploadPromise;
    } catch (error) {
      expect(error).toBeInstanceOf(DOMException);
      expect((error as DOMException).name).toBe('AbortError');
    }
  });

  it('works normally without signal (backward compat)', async () => {
    const file = new File(['content'], 'test.txt', { type: 'text/plain' });
    const onProgress = vi.fn();

    const uploadPromise = uploadFilesWithProgress([file], onProgress);

    mockXHR.status = 200;
    mockXHR.responseText = JSON.stringify({
      uploaded_count: 1,
      files: [{ file_id: '1', file_name: 'test.txt', file_url: '/f/1' }],
    });
    mockXHR.onload?.();

    const result = await uploadPromise;
    expect(result.uploaded_count).toBe(1);
    expect(result.files[0].fileName).toBe('test.txt');
  });
});
