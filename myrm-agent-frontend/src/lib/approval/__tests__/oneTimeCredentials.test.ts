import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  BLOCKED_CREDENTIAL_KEYS,
  OneTimeCredentialError,
  stageOneTimeCredentials,
  supportsOneTimeCredentials,
  wipeOneTimeCredentials,
} from '@/lib/approval/oneTimeCredentials';

vi.mock('@/lib/api', () => ({ API_BASE_URL: 'http://api.test/api/v1' }));

function respond(body: unknown, init: { ok: boolean; status?: number }) {
  return vi.fn().mockResolvedValue({
    ok: init.ok,
    status: init.status ?? (init.ok ? 200 : 400),
    json: async () => body,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('BLOCKED_CREDENTIAL_KEYS', () => {
  it('lists every name the server refuses (harness validate_credential_key)', () => {
    expect([...BLOCKED_CREDENTIAL_KEYS].sort()).toEqual(
      [
        'BASH_ENV',
        'DYLD_INSERT_LIBRARIES',
        'DYLD_LIBRARY_PATH',
        'ENV',
        'HOME',
        'IFS',
        'LD_LIBRARY_PATH',
        'LD_PRELOAD',
        'LOGNAME',
        'NODE_OPTIONS',
        'PATH',
        'PERL5LIB',
        'PROMPT_COMMAND',
        'PYTHONHOME',
        'PYTHONPATH',
        'RUBYLIB',
        'SHELL',
        'USER',
      ].sort(),
    );
  });
});

describe('supportsOneTimeCredentials', () => {
  it('is true only for the bash tool, whose executor delivers staged credentials', () => {
    expect(supportsOneTimeCredentials('bash_code_execute_tool')).toBe(true);
    for (const other of ['execute_code', 'shell', 'execute_command', 'run_script', 'file_read_tool']) {
      expect(supportsOneTimeCredentials(other)).toBe(false);
    }
  });
});

describe('stageOneTimeCredentials', () => {
  it('posts the chat, the command and the credentials, and returns handles without any secret', async () => {
    const fetchMock = respond({ staged: [{ handle_id: 'cred_ephemeral_1', key: 'DB_PASSWORD' }] }, { ok: true });
    vi.stubGlobal('fetch', fetchMock);

    const staged = await stageOneTimeCredentials('chat-1', 'psql -h db', [
      { key: 'DB_PASSWORD', secret: 'hunter2', ttlSeconds: 45 },
    ]);

    expect(staged).toEqual([{ handleId: 'cred_ephemeral_1', key: 'DB_PASSWORD' }]);
    expect(JSON.stringify(staged)).not.toContain('hunter2');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://api.test/api/v1/approvals/credentials');
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('include');
    expect(JSON.parse(init.body)).toEqual({
      chat_id: 'chat-1',
      command: 'psql -h db',
      credentials: [{ key: 'DB_PASSWORD', secret: 'hunter2', ttl_seconds: 45, single_use: true }],
    });
  });

  it.each([
    [400, 'Blocked credential key'],
    [422, [{ msg: 'bad' }]],
  ])('throws an error that carries only the status %i, never the server wording', async (status, detail) => {
    vi.stubGlobal('fetch', respond({ detail }, { ok: false, status }));

    const error = await stageOneTimeCredentials('chat-1', 'x', [{ key: 'PATH', secret: 's', ttlSeconds: 60 }]).catch(
      (e: unknown) => e,
    );

    expect(error).toBeInstanceOf(OneTimeCredentialError);
    expect(error).toMatchObject({ status, message: `HTTP ${status}` });
    expect(JSON.stringify(error)).not.toContain('Blocked credential key');
  });
});

describe('wipeOneTimeCredentials', () => {
  it('posts the handles to destroy', async () => {
    const fetchMock = respond({ wiped: 2 }, { ok: true });
    vi.stubGlobal('fetch', fetchMock);

    await wipeOneTimeCredentials('chat-1', ['h1', 'h2']);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://api.test/api/v1/approvals/credentials/wipe');
    expect(JSON.parse(init.body)).toEqual({ chat_id: 'chat-1', handle_ids: ['h1', 'h2'] });
  });

  it('does not call the server when there is nothing to destroy', async () => {
    const fetchMock = respond({ wiped: 0 }, { ok: true });
    vi.stubGlobal('fetch', fetchMock);

    await wipeOneTimeCredentials('chat-1', []);

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
