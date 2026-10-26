import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest } from '@/lib/api';
import {
  encodeUtf8Base64,
  readWorkspaceText,
  saveWorkspaceText,
  saveWorkspaceTextCopy,
  WorkspaceTextError,
} from '@/services/workspaceText';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

const decodeBase64 = (encoded: string): string => {
  const binary = atob(encoded);
  return new TextDecoder().decode(Uint8Array.from(binary, (char) => char.charCodeAt(0)));
};

const refusal = (status: number, ...details: Array<{ field: string; issue: string }>) =>
  new ApiError('server wording that must never reach the user', status, details);

beforeEach(() => {
  apiRequestMock.mockReset();
});

describe('encodeUtf8Base64', () => {
  it.each([
    ['empty text', ''],
    ['ASCII', 'hello\nworld\n'],
    ['accents and CJK', 'héllo 世界 こんにちは'],
    ['emoji outside the BMP', 'rocket \u{1F680} done'],
    ['markup a text sanitiser would strip', '<|endoftext|> \u001b[31mred\u001b[0m \ufffd'],
  ])('carries %s byte for byte', (_label, text) => {
    expect(decodeBase64(encodeUtf8Base64(text))).toBe(text);
  });

  it('handles a megabyte of text, which one spread call over its bytes could not', () => {
    const text = '世界-line\n'.repeat(120_000);
    expect(new TextEncoder().encode(text).length).toBeGreaterThan(1024 * 1024);

    expect(decodeBase64(encodeUtf8Base64(text))).toBe(text);
  });
});

describe('readWorkspaceText', () => {
  it('asks for the file by workspace and path, leaves failures to the caller, and renames the server fields', async () => {
    apiRequestMock.mockResolvedValue({
      path: '/ws/a b.txt',
      name: 'a b.txt',
      content: 'hi\n',
      version: 'abc',
      size: 4,
      editable: false,
      readonly_reason: 'mixed_line_endings',
      truncated: false,
    });

    const snapshot = await readWorkspaceText('/ws', '/ws/a b.txt');

    expect(apiRequestMock).toHaveBeenCalledWith(`/files/browse/text?workspace=%2Fws&path=%2Fws%2Fa+b.txt`, {
      silent: true,
    });
    expect(snapshot).toEqual({
      path: '/ws/a b.txt',
      name: 'a b.txt',
      content: 'hi\n',
      version: 'abc',
      size: 4,
      editable: false,
      readonlyReason: 'mixed_line_endings',
      truncated: false,
    });
  });

  it('lets a failure with no named reason through untouched', async () => {
    const failure = refusal(500);
    apiRequestMock.mockRejectedValue(failure);

    await expect(readWorkspaceText('/ws', 'a.txt')).rejects.toBe(failure);
  });
});

describe('saveWorkspaceText', () => {
  it('sends the text as base64 together with the version it was read at, and never as plain text', async () => {
    apiRequestMock.mockResolvedValue({ path: '/ws/a.txt', name: 'a.txt', version: 'v2', size: 5, changed: true });

    const result = await saveWorkspaceText('/ws', '/ws/a.txt', 'héllo', 'v1');

    expect(result.version).toBe('v2');
    const [endpoint, init] = apiRequestMock.mock.calls[0];
    expect(endpoint).toBe('/files/browse/text');
    expect(init).toMatchObject({ method: 'PUT', silent: true });
    const body = JSON.parse(String(init?.body));
    expect(Object.keys(body).sort()).toEqual(['base_version', 'content_b64', 'path', 'workspace']);
    expect(body.base_version).toBe('v1');
    expect(decodeBase64(body.content_b64)).toBe('héllo');
  });

  it('turns a refusal for a changed file into a typed error carrying the version to overwrite', async () => {
    apiRequestMock.mockRejectedValue(
      refusal(409, { field: 'reason', issue: 'version_conflict' }, { field: 'current_version', issue: 'f'.repeat(64) }),
    );

    const error = await saveWorkspaceText('/ws', 'a.txt', 'x', 'v1').catch((e: unknown) => e);

    expect(error).toBeInstanceOf(WorkspaceTextError);
    expect(error).toMatchObject({ reason: 'version_conflict', currentVersion: 'f'.repeat(64) });
    expect((error as Error).message).not.toContain('server wording');
  });

  it.each(['write_blocked', 'not_found', 'invalid_content', 'content_too_large', 'binary', 'too_large'])(
    'names the %s refusal',
    async (reason) => {
      apiRequestMock.mockRejectedValue(refusal(400, { field: 'reason', issue: reason }));

      await expect(saveWorkspaceText('/ws', 'a.txt', 'x', 'v1')).rejects.toMatchObject({
        reason,
        currentVersion: null,
      });
    },
  );

  it('passes a reason it does not know, a refusal without one, and a network failure through as they came', async () => {
    const unknownReason = refusal(400, { field: 'reason', issue: 'something_new' });
    const noReason = refusal(400, { field: 'other', issue: 'x' });
    const offline = new TypeError('Failed to fetch');

    apiRequestMock.mockRejectedValueOnce(unknownReason).mockRejectedValueOnce(noReason).mockRejectedValueOnce(offline);

    await expect(saveWorkspaceText('/ws', 'a.txt', 'x', 'v1')).rejects.toBe(unknownReason);
    await expect(saveWorkspaceText('/ws', 'a.txt', 'x', 'v1')).rejects.toBe(noReason);
    await expect(saveWorkspaceText('/ws', 'a.txt', 'x', 'v1')).rejects.toBe(offline);
  });
});

describe('saveWorkspaceTextCopy', () => {
  it('posts the text as base64 to the copy endpoint and returns the new file', async () => {
    apiRequestMock.mockResolvedValue({
      path: '/ws/a (1).txt',
      name: 'a (1).txt',
      version: 'v9',
      size: 2,
      changed: true,
    });

    const result = await saveWorkspaceTextCopy('/ws', '/ws/a.txt', 'ok');

    expect(result.name).toBe('a (1).txt');
    const [endpoint, init] = apiRequestMock.mock.calls[0];
    expect(endpoint).toBe('/files/browse/text/copy');
    expect(init).toMatchObject({ method: 'POST', silent: true });
    const body = JSON.parse(String(init?.body));
    expect(Object.keys(body).sort()).toEqual(['content_b64', 'path', 'workspace']);
    expect(decodeBase64(body.content_b64)).toBe('ok');
  });
});
