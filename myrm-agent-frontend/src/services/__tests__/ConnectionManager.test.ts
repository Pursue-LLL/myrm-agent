/**
 * The workspace stream connection: one SSE connection that carries the status of every chat session. A turn's own
 * content never travels on it, so a content frame from the server is ignored and nothing accumulates for it.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type StreamOptions = {
  onopen: (response: Response) => Promise<void>;
  onmessage: (event: { event: string; data: string }) => void;
};

const harness = vi.hoisted(() => ({
  options: null as StreamOptions | null,
  chat: { setSessionStatus: vi.fn(), initSessionStatuses: vi.fn() },
  apiRequest: vi.fn(),
}));

vi.mock('@microsoft/fetch-event-source', () => ({
  fetchEventSource: vi.fn((_url: string, options: StreamOptions) => {
    harness.options = options;
    return new Promise<void>(() => undefined);
  }),
}));
vi.mock('@/lib/api', () => ({
  getApiUrl: (path: string) => `http://api.test/api/v1${path}`,
  apiRequest: harness.apiRequest,
}));
vi.mock('@/lib/deploy-mode', () => ({
  getApiBaseUrl: () => 'http://api.test/api/v1',
  resolveE2eApiBase: () => null,
}));
vi.mock('@/lib/utils/authHeaders', () => ({ getAuthHeaders: () => ({}) }));
vi.mock('@/store/useChatStore', () => ({ default: { getState: () => harness.chat } }));

import { fetchEventSource } from '@microsoft/fetch-event-source';
import { connectionManager } from '../ConnectionManager';

const RECONNECTED_EVENT = 'myrm_workspace_stream_reconnected';
const STREAM_RESPONSE = () => new Response('', { status: 200, headers: { 'content-type': 'text/event-stream' } });

function openedStream(): StreamOptions {
  if (!harness.options) {
    throw new Error('the workspace stream was never opened');
  }
  return harness.options;
}

describe('ConnectionManager', () => {
  beforeEach(() => {
    harness.options = null;
    harness.chat.setSessionStatus.mockReset();
    harness.chat.initSessionStatuses.mockReset();
    harness.apiRequest
      .mockReset()
      .mockResolvedValue({ activeSessions: [{ chatId: 'chat-live', agentType: 'general' }] });
    vi.mocked(fetchEventSource).mockClear();
  });

  afterEach(() => {
    connectionManager.disconnect();
    vi.restoreAllMocks();
  });

  it('opens the workspace stream once, however often it is asked to connect', () => {
    connectionManager.connect();
    connectionManager.connect();

    expect(fetchEventSource).toHaveBeenCalledTimes(1);
    expect(vi.mocked(fetchEventSource).mock.calls[0]?.[0]).toBe('http://api.test/api/v1/workspace/stream');
  });

  it('announces readiness and seeds the sidebar from the sessions generating right now once the stream opens', async () => {
    const ready = vi.fn();
    window.addEventListener('myrm_workspace_stream_ready', ready);
    connectionManager.connect();

    await openedStream().onopen(STREAM_RESPONSE());

    expect(ready).toHaveBeenCalledTimes(1);
    await vi.waitFor(() =>
      expect(harness.chat.initSessionStatuses).toHaveBeenCalledWith({ 'chat-live': 'generating' }),
    );
    window.removeEventListener('myrm_workspace_stream_ready', ready);
  });

  it('refuses a response that is not an event stream', async () => {
    connectionManager.connect();

    await expect(openedStream().onopen(new Response('', { status: 502 }))).rejects.toThrow(
      'Failed to connect to workspace stream',
    );
  });

  it('shows a session_status frame as the status of that chat', () => {
    connectionManager.connect();

    openedStream().onmessage({
      event: 'session_status',
      data: JSON.stringify({ chat_id: 'chat-1', status: 'awaiting_approval', agent_type: 'general' }),
    });

    expect(harness.chat.setSessionStatus).toHaveBeenCalledWith('chat-1', 'awaiting_approval');
  });

  it('logs and skips a session_status frame it cannot parse', () => {
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    connectionManager.connect();

    openedStream().onmessage({ event: 'session_status', data: '{not json' });

    expect(harness.chat.setSessionStatus).not.toHaveBeenCalled();
    expect(logged).toHaveBeenCalledTimes(1);
  });

  it('announces a reconnect so views resync, but not the first connection', async () => {
    const reconnected = vi.fn();
    window.addEventListener(RECONNECTED_EVENT, reconnected);
    connectionManager.connect();

    await openedStream().onopen(STREAM_RESPONSE());
    expect(reconnected).not.toHaveBeenCalled();

    await openedStream().onopen(STREAM_RESPONSE());
    expect(reconnected).toHaveBeenCalledTimes(1);
    window.removeEventListener(RECONNECTED_EVENT, reconnected);
  });

  it('does not consume turn content: a content frame is ignored and no content hook exists', () => {
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    connectionManager.connect();

    openedStream().onmessage({
      event: 'multiplex',
      data: JSON.stringify({ chat_id: 'chat-1', message_id: 'msg-1', raw_chunk: 'data: {"type":"message"}\n\n' }),
    });

    expect(logged).not.toHaveBeenCalled();
    expect(harness.chat.setSessionStatus).not.toHaveBeenCalled();
    expect('registerMultiplexHandler' in connectionManager).toBe(false);
    expect('__MYRM_MULTIPLEX_STATS__' in window).toBe(false);
  });
});
