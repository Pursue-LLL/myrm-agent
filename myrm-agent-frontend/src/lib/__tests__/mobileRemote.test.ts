import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { E2EEHandshakeRequiredError } from '@/lib/e2ee/client';

import {
  buildMobileHubUrl,
  ensureMobileE2EE,
  isMobileRemotePath,
  mobileApiRequest,
  mobileRemotePost,
  storeMobilePairToken,
  withMobilePairHeaders,
} from '../mobileRemote';
import { BACKEND, jsonResponse, kit, SESSION } from './mobileRemoteKit';

vi.mock('@/lib/e2ee/client', async () => (await import('./mobileRemoteKit')).e2eeClientMock());
vi.mock('@/lib/utils/apiConfig', async () => (await import('./mobileRemoteKit')).apiConfigMock());

const SERVER_KEY = 'c2VydmVyLWtleQ';
const fetchMock = vi.fn<typeof fetch>();

/** Pretends a handshake succeeded: the session is stored, so later reads find it. */
const handshakeSucceeds = () =>
  kit.ensureE2EEHandshake.mockImplementation(() => {
    kit.loadStoredE2EESession.mockReturnValue(SESSION);
    return Promise.resolve(SESSION);
  });

beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  window.history.replaceState(null, '', '/mobile');
  kit.loadStoredE2EESession.mockReturnValue(null);
  kit.e2eeRequestHeaders.mockReturnValue({ 'X-E2EE-Session': SESSION.sessionId });
  kit.encryptPairToken.mockImplementation((_session, token) => `sealed(${token})`);
  kit.encryptJsonBody.mockImplementation((_session, body) => `sealed(${body})`);
  fetchMock.mockResolvedValue(jsonResponse({ data: { ok: true } }));
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('isMobileRemotePath', () => {
  it('matches the hub and every page below it', () => {
    expect(isMobileRemotePath('/mobile')).toBe(true);
    expect(isMobileRemotePath('/mobile/status/c-1')).toBe(true);
    expect(isMobileRemotePath('/mobile/takeover/c-1')).toBe(true);
  });

  it('leaves lookalike and unrelated routes inside the desktop shell', () => {
    expect(isMobileRemotePath('/mobile-app')).toBe(false);
    expect(isMobileRemotePath('/settings/mobile')).toBe(false);
    expect(isMobileRemotePath('/')).toBe(false);
  });
});

describe('ensureMobileE2EE', () => {
  it('reuses the stored session without a new handshake', async () => {
    kit.loadStoredE2EESession.mockReturnValue(SESSION);
    kit.readServerPublicKeyFromLocation.mockReturnValue(SERVER_KEY);

    await expect(ensureMobileE2EE()).resolves.toBe(SESSION);

    expect(kit.ensureE2EEHandshake).not.toHaveBeenCalled();
  });

  it('stays unencrypted when the address carries no server key', async () => {
    await expect(ensureMobileE2EE()).resolves.toBeNull();

    expect(kit.ensureE2EEHandshake).not.toHaveBeenCalled();
  });

  it('shakes hands with the backend when the address carries a server key', async () => {
    kit.readServerPublicKeyFromLocation.mockReturnValue(SERVER_KEY);
    kit.ensureE2EEHandshake.mockResolvedValue(SESSION);

    await expect(ensureMobileE2EE()).resolves.toBe(SESSION);

    expect(kit.ensureE2EEHandshake).toHaveBeenCalledWith(BACKEND);
  });

  it('refuses to go on when the handshake fails', async () => {
    kit.readServerPublicKeyFromLocation.mockReturnValue(SERVER_KEY);
    kit.ensureE2EEHandshake.mockResolvedValue(null);

    await expect(ensureMobileE2EE()).rejects.toBeInstanceOf(E2EEHandshakeRequiredError);
  });
});

describe('withMobilePairHeaders', () => {
  it('hands back a copy of the headers when nothing is paired', () => {
    const given = { Accept: 'application/json' };

    const headers = withMobilePairHeaders(given);

    expect(headers).toEqual({ Accept: 'application/json' });
    expect(headers).not.toBe(given);
    expect(withMobilePairHeaders()).toEqual({});
  });

  it('adds the plain pair token next to the given headers without touching them', () => {
    storeMobilePairToken('pair-1');
    const given = { Accept: 'application/json' };

    expect(withMobilePairHeaders(given)).toEqual({ Accept: 'application/json', 'X-Pair-Token': 'pair-1' });
    expect(given).toEqual({ Accept: 'application/json' });
  });

  it('never sends the plain token when the address announces an encrypted channel', () => {
    storeMobilePairToken('pair-1');
    kit.readServerPublicKeyFromLocation.mockReturnValue(SERVER_KEY);

    expect(() => withMobilePairHeaders()).toThrow(E2EEHandshakeRequiredError);
  });

  it('adds only the session headers when a session exists but nothing is paired', () => {
    kit.loadStoredE2EESession.mockReturnValue(SESSION);

    expect(withMobilePairHeaders({ Accept: 'application/json' })).toEqual({
      Accept: 'application/json',
      'X-E2EE-Session': 'session-1',
    });
    expect(kit.encryptPairToken).not.toHaveBeenCalled();
  });

  it('seals the pair token instead of sending it when a session exists', () => {
    storeMobilePairToken('pair-1');
    kit.loadStoredE2EESession.mockReturnValue(SESSION);

    const headers = withMobilePairHeaders();

    expect(headers).toEqual({ 'X-E2EE-Session': 'session-1', 'X-E2EE-Pair-Token': 'sealed(pair-1)' });
    expect(kit.encryptPairToken).toHaveBeenCalledWith(SESSION, 'pair-1');
  });

  it('lets the session headers win over a header of the same name', () => {
    kit.loadStoredE2EESession.mockReturnValue(SESSION);

    expect(withMobilePairHeaders({ 'X-E2EE-Session': 'caller' })['X-E2EE-Session']).toBe('session-1');
  });
});

describe('buildMobileHubUrl', () => {
  it('prefers the tunnel, then the ingress, then the origin of this page', () => {
    expect(buildMobileHubUrl('/mobile', 'https://tunnel.example', 'https://ingress.example')).toBe(
      'https://tunnel.example/mobile',
    );
    expect(buildMobileHubUrl('/mobile', '', 'https://ingress.example')).toBe('https://ingress.example/mobile');
    expect(buildMobileHubUrl('/mobile', '', '')).toBe(`${window.location.origin}/mobile`);
  });

  it('joins base and path with exactly one slash', () => {
    expect(buildMobileHubUrl('mobile/hub', 'https://tunnel.example/', '')).toBe('https://tunnel.example/mobile/hub');
    expect(buildMobileHubUrl('/mobile/hub', 'https://tunnel.example', '')).toBe('https://tunnel.example/mobile/hub');
  });

  it('returns the path as given when there is no base to put it on', () => {
    vi.stubGlobal('window', undefined);

    expect(buildMobileHubUrl('mobile', '', '')).toBe('mobile');
  });

  it('carries the server key in the fragment, replacing a fragment of the path', () => {
    expect(buildMobileHubUrl('/mobile#old', 'https://tunnel.example', '', 'a+b/c=')).toBe(
      'https://tunnel.example/mobile#e2ee=a%2Bb%2Fc%3D',
    );
  });

  it('adds no fragment without a server key', () => {
    expect(buildMobileHubUrl('/mobile#kept', 'https://tunnel.example', '')).toBe('https://tunnel.example/mobile#kept');
    expect(buildMobileHubUrl('/mobile', 'https://tunnel.example', '', '')).toBe('https://tunnel.example/mobile');
  });
});

describe('mobileApiRequest sending', () => {
  it('calls the backend with the session cookie and the pair token', async () => {
    storeMobilePairToken('pair-1');

    await mobileApiRequest('/api/v1/chats', { method: 'GET' });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BACKEND}/api/v1/chats`);
    expect(init).toEqual({
      method: 'GET',
      headers: { 'X-Pair-Token': 'pair-1' },
      body: undefined,
      credentials: 'include',
    });
  });

  it('sends no pair header before a phone was paired', async () => {
    await mobileApiRequest('/api/v1/chats');

    expect(fetchMock.mock.calls[0][1]?.headers).toEqual({});
  });

  it('keeps the headers and the text body it was given when nothing is encrypted', async () => {
    await mobileApiRequest('/api/v1/chats', {
      method: 'POST',
      headers: new Headers({ 'X-Custom': '1' }),
      body: '{"a":1}',
    });

    const init = fetchMock.mock.calls[0][1];
    expect(init?.headers).toEqual({ 'x-custom': '1' });
    expect(init?.body).toBe('{"a":1}');
    expect(kit.encryptJsonBody).not.toHaveBeenCalled();
  });

  it('seals the pair token and a text body when a session exists', async () => {
    storeMobilePairToken('pair-1');
    kit.loadStoredE2EESession.mockReturnValue(SESSION);

    await mobileApiRequest('/api/v1/chats', { method: 'POST', body: '{"a":1}' });

    const init = fetchMock.mock.calls[0][1];
    expect(init?.headers).toEqual({ 'X-E2EE-Session': 'session-1', 'X-E2EE-Pair-Token': 'sealed(pair-1)' });
    expect(init?.body).toBe('sealed({"a":1})');
    expect(kit.encryptJsonBody).toHaveBeenCalledWith(SESSION, '{"a":1}');
  });

  it.each([
    ['no body', undefined],
    ['an empty body', ''],
    ['a body that is not text', new URLSearchParams('a=1')],
  ])('does not seal %s', async (_name, body) => {
    kit.loadStoredE2EESession.mockReturnValue(SESSION);

    await mobileApiRequest('/api/v1/chats', { method: 'POST', body });

    expect(fetchMock.mock.calls[0][1]?.body).toBe(body);
    expect(kit.encryptJsonBody).not.toHaveBeenCalled();
  });

  it('shakes hands before sending, so the very first request is already sealed', async () => {
    kit.readServerPublicKeyFromLocation.mockReturnValue(SERVER_KEY);
    handshakeSucceeds();

    await mobileApiRequest('/api/v1/chats', { method: 'POST', body: '{}' });

    expect(kit.ensureE2EEHandshake).toHaveBeenCalledWith(BACKEND);
    expect(kit.ensureE2EEHandshake.mock.invocationCallOrder[0]).toBeLessThan(fetchMock.mock.invocationCallOrder[0]);
    expect(fetchMock.mock.calls[0][1]?.headers).toMatchObject({ 'X-E2EE-Session': 'session-1' });
    expect(fetchMock.mock.calls[0][1]?.body).toBe('sealed({})');
  });

  it('does not send anything when the handshake fails', async () => {
    kit.readServerPublicKeyFromLocation.mockReturnValue(SERVER_KEY);
    kit.ensureE2EEHandshake.mockResolvedValue(null);

    await expect(mobileApiRequest('/api/v1/chats')).rejects.toBeInstanceOf(E2EEHandshakeRequiredError);

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('mobileApiRequest answers', () => {
  it('fails with the status when the server refuses', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'nope' }, 503));

    await expect(mobileApiRequest('/api/v1/chats')).rejects.toThrow('Mobile API failed: 503');
  });

  it.each([
    ['unwraps the data of an envelope', { success: true, data: { a: 1 } }, { a: 1 }],
    ['returns null data as it is', { success: true, data: null }, null],
    ['returns an object without data whole', { success: true }, { success: true }],
    ['returns a list whole', [1, 2], [1, 2]],
    ['returns null as it is', null, null],
    ['returns plain text as it is', 'ok', 'ok'],
  ])('%s', async (_name, payload, expected) => {
    fetchMock.mockResolvedValue(jsonResponse(payload));

    await expect(mobileApiRequest('/api/v1/chats')).resolves.toEqual(expected);
  });

  it('opens a sealed answer when a session exists, then unwraps its data', async () => {
    const sealed = { v: 1, c: 'cipher' };
    kit.loadStoredE2EESession.mockReturnValue(SESSION);
    kit.decryptJsonPayload.mockReturnValue({ success: true, data: { secret: true } });
    fetchMock.mockResolvedValue(jsonResponse(sealed));

    await expect(mobileApiRequest('/api/v1/chats')).resolves.toEqual({ secret: true });

    expect(kit.decryptJsonPayload).toHaveBeenCalledWith(SESSION, sealed);
  });

  it.each([
    ['a plain answer', { detail: 'plain' }],
    ['an empty answer', null],
  ])('does not try to open %s even when a session exists', async (_name, payload) => {
    kit.loadStoredE2EESession.mockReturnValue(SESSION);
    fetchMock.mockResolvedValue(jsonResponse(payload));

    await expect(mobileApiRequest('/api/v1/chats')).resolves.toEqual(payload);

    expect(kit.decryptJsonPayload).not.toHaveBeenCalled();
  });

  it('hands a sealed-looking answer back untouched when there is no session to open it with', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ v: 1, c: 'cipher' }));

    await expect(mobileApiRequest('/api/v1/chats')).resolves.toEqual({ v: 1, c: 'cipher' });

    expect(kit.decryptJsonPayload).not.toHaveBeenCalled();
  });
});

describe('mobileRemotePost', () => {
  it('sends JSON bodies with an explicit application/json content type', async () => {
    const body = { agent_id: 'builtin-general', project_id: null, initial_message: '帮我调研三家竞品的定价策略' };

    await mobileRemotePost('/api/v1/remote-access/mobile/spawn', body);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BACKEND}/api/v1/remote-access/mobile/spawn`);
    expect(init?.method).toBe('POST');
    // FastAPI only parses a JSON body when the content type declares it; a
    // missing header makes every remote POST fail with 422 "field required".
    expect(init?.headers).toMatchObject({ 'Content-Type': 'application/json' });
    expect(JSON.parse(init?.body as string)).toEqual(body);
  });

  it('answers with the data of the envelope', async () => {
    await expect(mobileRemotePost('/api/v1/remote-access/mobile/spawn', {})).resolves.toEqual({ ok: true });
  });
});
