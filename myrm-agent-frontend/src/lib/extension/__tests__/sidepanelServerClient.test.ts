/**
 * @vitest-environment node
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createServerClient } from '../../../../../myrm-agent-extension/src/sidepanel/server_client.js';

type StorageChange = (changes: Record<string, unknown>) => void;

/** Boots a client against stored settings; `answer` is what the server replies to each request. */
function bootClient(
  settings: Record<string, string>,
  answer: () => Promise<Response> = async () => new Response('{}'),
) {
  const statuses: string[] = [];
  const changeListeners: StorageChange[] = [];
  const fetchMock = vi.fn(async (_url: string, _init: RequestInit) => answer());
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('chrome', {
    storage: {
      local: { get: (_keys: string[], callback: (data: object) => void) => callback(settings) },
      onChanged: { addListener: (listener: StorageChange) => changeListeners.push(listener) },
    },
  });
  const client = createServerClient((status: string) => statuses.push(status));
  client.start();
  return { client, statuses, fetchMock, changeListeners };
}

const settled = () => new Promise((resolve) => setTimeout(resolve, 0));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('server client', () => {
  it.each([
    ['ws://localhost:25808/api/v1/ws/extension', 'http://localhost:25808'],
    ['wss://agent.example.com/api/v1/ws/extension/', 'https://agent.example.com'],
    ['ws://localhost:25808/ws/extension', 'http://localhost:25808'],
    ['http://localhost:25808/', 'http://localhost:25808'],
  ])('reaches the server behind the bridge URL %s', async (serverUrl, base) => {
    const { fetchMock } = bootClient({ serverUrl });
    await settled();

    expect(fetchMock.mock.calls[0][0]).toBe(`${base}/api/v1/health`);
  });

  it('reports connecting, then connected once the server answers', async () => {
    const { statuses } = bootClient({ serverUrl: 'ws://localhost:25808/api/v1/ws/extension' });
    await settled();

    expect(statuses).toEqual(['connecting', 'connected']);
  });

  it.each([
    ['answers with an error', async () => new Response('no', { status: 503 })],
    [
      'cannot be reached',
      async () => {
        throw new TypeError('Failed to fetch');
      },
    ],
  ])('reports an error when the server %s', async (_label, answer) => {
    const { statuses } = bootClient({ serverUrl: 'ws://localhost:25808/api/v1/ws/extension' }, answer);
    await settled();

    expect(statuses).toEqual(['connecting', 'error']);
  });

  it('reports disconnected, and asks nobody, when no server is configured', async () => {
    const { statuses, fetchMock } = bootClient({});
    await settled();

    expect(statuses).toEqual(['disconnected']);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('sends the bearer token, and lets a request override the headers', async () => {
    const { client, fetchMock } = bootClient({ serverUrl: 'ws://h:1/api/v1/ws/extension', authToken: 'secret' });
    await settled();

    await client.apiFetch('/api/v1/agents/agent-stream', { method: 'POST', headers: { Accept: 'text/event-stream' } });

    const [url, init] = fetchMock.mock.calls.at(-1) ?? [];
    expect(url).toBe('http://h:1/api/v1/agents/agent-stream');
    expect(init?.headers).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer secret',
      Accept: 'text/event-stream',
    });
  });

  it('sends no Authorization header without a token', async () => {
    const { client, fetchMock } = bootClient({ serverUrl: 'ws://h:1/api/v1/ws/extension' });
    await settled();

    await client.apiFetch('/api/v1/health');

    expect(fetchMock.mock.calls.at(-1)?.[1]?.headers).toEqual({ 'Content-Type': 'application/json' });
  });

  it('checks the connection again when the server URL or token changes, and for nothing else', async () => {
    const { statuses, changeListeners } = bootClient({ serverUrl: 'ws://h:1/api/v1/ws/extension' });
    await settled();
    expect(statuses).toHaveLength(2);

    changeListeners[0]({ authorizedDomains: {} });
    await settled();
    expect(statuses).toHaveLength(2);

    changeListeners[0]({ serverUrl: {} });
    await settled();
    expect(statuses).toHaveLength(4);

    changeListeners[0]({ authToken: {} });
    await settled();
    expect(statuses).toHaveLength(6);
  });
});
