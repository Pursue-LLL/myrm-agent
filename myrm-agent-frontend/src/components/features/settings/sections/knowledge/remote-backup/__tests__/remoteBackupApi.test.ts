import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchWithTimeout = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ fetchWithTimeout }));

import {
  checkConnection,
  deleteBackup,
  errorCodeKey,
  fetchAutoStatus,
  listBackups,
  restoreBackup,
  runBackup,
} from '../remoteBackupApi';
import { DEFAULT_CONFIG } from '../remoteBackupConfig';

const webdav = {
  ...DEFAULT_CONFIG,
  deviceName: 'Office',
  maxBackups: 5,
  webdav: { host: 'https://dav.example.com', username: 'me', password: 'secret', path: '/backups' },
};
const s3 = {
  ...DEFAULT_CONFIG,
  provider: 's3' as const,
  s3: {
    endpoint: 'https://s3.example.com',
    region: 'eu-1',
    bucket: 'mine',
    accessKeyId: 'AKIA',
    secretAccessKey: 'shh',
    prefix: 'myrm/',
    forcePathStyle: true,
  },
};

function reply(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

function sentBody(call = 0): Record<string, unknown> {
  return JSON.parse(fetchWithTimeout.mock.calls[call][1].body as string);
}

beforeEach(() => {
  fetchWithTimeout.mockReset();
});

describe('what a call sends', () => {
  it('tells the server what is on screen: provider, device, count to keep and the WebDAV details', async () => {
    fetchWithTimeout.mockResolvedValue(reply({ files: [] }));

    await listBackups(webdav);

    const [url, init] = fetchWithTimeout.mock.calls[0];
    expect(url).toBe('/memory/backup/remote/list');
    expect(init.method).toBe('POST');
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
    expect(sentBody()).toEqual({
      provider: 'webdav',
      device_name: 'Office',
      max_backups: 5,
      webdav: webdav.webdav,
    });
  });

  it('renames the S3 settings the way the server spells them', async () => {
    fetchWithTimeout.mockResolvedValue(reply({ files: [] }));

    await listBackups(s3);

    expect(sentBody().s3).toEqual({
      endpoint: 'https://s3.example.com',
      region: 'eu-1',
      bucket: 'mine',
      access_key_id: 'AKIA',
      secret_access_key: 'shh',
      prefix: 'myrm/',
      force_path_style: true,
    });
    expect(sentBody()).not.toHaveProperty('webdav');
  });
});

describe('listBackups', () => {
  it('returns the backups the server found', async () => {
    const files = [{ file_name: 'a.json.gz', modified_time: '2026-10-26T12:00:00Z', size_bytes: 12 }];
    fetchWithTimeout.mockResolvedValue(reply({ files }));

    await expect(listBackups(webdav)).resolves.toEqual(files);
  });

  it('is empty only when the server says the storage is empty', async () => {
    fetchWithTimeout.mockResolvedValue(reply({}));

    await expect(listBackups(webdav)).resolves.toEqual([]);
  });

  it('throws when the server could not read the storage, instead of reading as an empty one', async () => {
    fetchWithTimeout.mockResolvedValue(reply({ detail: 'refused' }, 502));

    await expect(listBackups(webdav)).rejects.toThrow('502');
  });
});

describe('checkConnection', () => {
  it('is true only when the server connected', async () => {
    fetchWithTimeout.mockResolvedValueOnce(reply({ connected: true }));
    fetchWithTimeout.mockResolvedValueOnce(reply({ connected: false }));
    fetchWithTimeout.mockResolvedValueOnce(reply({ detail: 'bad request' }, 422));

    expect(await checkConnection(webdav)).toBe(true);
    expect(await checkConnection(webdav)).toBe(false);
    expect(await checkConnection(webdav)).toBe(false);
  });
});

describe('runBackup', () => {
  it('reports success', async () => {
    fetchWithTimeout.mockResolvedValue(reply({ success: true, error: null, error_code: null }));

    await expect(runBackup(webdav)).resolves.toEqual({ success: true, errorCode: null });
  });

  it('reports the stable code of a failure, never the server wording', async () => {
    fetchWithTimeout.mockResolvedValue(
      reply({ success: false, error: 'Remote upload failed after retries', error_code: 'upload' }),
    );

    const result = await runBackup(webdav);

    expect(result).toEqual({ success: false, errorCode: 'upload' });
    expect(JSON.stringify(result)).not.toContain('retries');
  });

  it('reports a refused request as a failure without a code', async () => {
    fetchWithTimeout.mockResolvedValue(reply({ detail: 'bad request' }, 422));

    await expect(runBackup(webdav)).resolves.toEqual({ success: false, errorCode: null });
  });

  it('never gives up on a snapshot that is still moving', async () => {
    fetchWithTimeout.mockResolvedValue(reply({ success: true }));

    await runBackup(webdav);

    expect(fetchWithTimeout.mock.calls[0][2]).toBe(0);
  });
});

describe('restoreBackup', () => {
  it('names the backup and reports how many memories came back', async () => {
    fetchWithTimeout.mockResolvedValue(reply({ success: true, restored_count: 42 }));

    const result = await restoreBackup(webdav, 'a.json.gz');

    expect(result).toEqual({ success: true, restoredCount: 42 });
    expect(fetchWithTimeout.mock.calls[0][0]).toBe('/memory/backup/remote/restore');
    expect(sentBody().file_name).toBe('a.json.gz');
    expect(fetchWithTimeout.mock.calls[0][2]).toBe(0);
  });

  it('is a failure when the server refuses or reports one', async () => {
    fetchWithTimeout.mockResolvedValueOnce(reply({ success: false, error: 'Failed to download' }));
    fetchWithTimeout.mockResolvedValueOnce(reply({}, 500));

    expect(await restoreBackup(webdav, 'a.json.gz')).toEqual({ success: false, restoredCount: 0 });
    expect(await restoreBackup(webdav, 'a.json.gz')).toEqual({ success: false, restoredCount: 0 });
  });
});

describe('deleteBackup', () => {
  it('is true only when the server deleted the backup', async () => {
    fetchWithTimeout.mockResolvedValueOnce(reply({ success: true }));
    fetchWithTimeout.mockResolvedValueOnce(reply({ success: false }));
    fetchWithTimeout.mockResolvedValueOnce(reply({}, 500));

    expect(await deleteBackup(webdav, 'a.json.gz')).toBe(true);
    expect(await deleteBackup(webdav, 'a.json.gz')).toBe(false);
    expect(await deleteBackup(webdav, 'a.json.gz')).toBe(false);
    expect(fetchWithTimeout.mock.calls[0][0]).toBe('/memory/backup/remote/delete');
    expect(sentBody().file_name).toBe('a.json.gz');
  });
});

describe('fetchAutoStatus', () => {
  it('reads how the scheduled backup is doing', async () => {
    const status = { last_success_at: null, last_attempt_at: null, last_error_code: 'upload', consecutive_failures: 2 };
    fetchWithTimeout.mockResolvedValue(reply(status));

    await expect(fetchAutoStatus()).resolves.toEqual(status);
    expect(fetchWithTimeout.mock.calls[0][0]).toBe('/memory/backup/remote/auto-status');
  });

  it('is unknown, not healthy, when the server cannot say', async () => {
    fetchWithTimeout.mockResolvedValue(reply({}, 500));

    await expect(fetchAutoStatus()).resolves.toBeNull();
  });
});

describe('errorCodeKey', () => {
  it.each(['config', 'snapshot', 'upload', 'busy', 'internal'])('knows %s', (code) => {
    expect(errorCodeKey(code)).toBe(code);
  });

  it.each(['somethingNew', '', null, undefined])('reads %j as an internal error', (code) => {
    expect(errorCodeKey(code)).toBe('internal');
  });
});
