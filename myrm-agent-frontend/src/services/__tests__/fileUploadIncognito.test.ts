import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { uploadFiles, uploadFilesWithProgress } from '../file';

const apiRequest = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({
  apiRequest,
  getApiUrl: (path: string) => `http://api.test${path}`,
}));

const RESPONSE = { uploaded_count: 1, files: [{ file_id: '1', file_name: 'a.txt', file_url: '/f/1' }] };
const file = () => new File(['content'], 'a.txt', { type: 'text/plain' });

describe('upload binding to an incognito chat', () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue(RESPONSE);
  });

  it('sends the chat id with a fetch upload only when one is given', async () => {
    await uploadFiles([file()], undefined, { incognitoChatId: 'chat-incognito' });
    await uploadFiles([file()]);

    const [bound, unbound] = apiRequest.mock.calls.map(([, init]) => init.body as FormData);
    expect(bound.get('chat_id')).toBe('chat-incognito');
    expect(unbound.has('chat_id')).toBe(false);
  });

  describe('with progress', () => {
    let sent: FormData[];
    let originalXHR: typeof XMLHttpRequest;

    beforeEach(() => {
      sent = [];
      originalXHR = globalThis.XMLHttpRequest;
      globalThis.XMLHttpRequest = function () {
        const xhr = {
          open: vi.fn(),
          setRequestHeader: vi.fn(),
          upload: {},
          status: 200,
          responseText: JSON.stringify(RESPONSE),
          onload: null as (() => void) | null,
          onerror: null,
          send: (body: FormData) => {
            sent.push(body);
            queueMicrotask(() => xhr.onload?.());
          },
        };
        return xhr;
      } as unknown as typeof XMLHttpRequest;
    });

    afterEach(() => {
      globalThis.XMLHttpRequest = originalXHR;
    });

    it('sends the chat id with an XHR upload only when one is given', async () => {
      await uploadFilesWithProgress([file()], vi.fn(), undefined, { incognitoChatId: 'chat-incognito' });
      await uploadFilesWithProgress([file()], vi.fn());

      expect(sent[0].get('chat_id')).toBe('chat-incognito');
      expect(sent[1].has('chat_id')).toBe(false);
    });
  });
});
