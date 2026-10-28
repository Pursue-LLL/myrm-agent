import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useStagedCredentials } from '@/hooks/approval/useStagedCredentials';

const client = vi.hoisted(() => ({
  stageOneTimeCredentials: vi.fn(),
  wipeOneTimeCredentials: vi.fn(),
}));
vi.mock('@/lib/approval/oneTimeCredentials', () => client);

const CREDENTIALS = [
  { key: 'DB_PASSWORD', secret: 'hunter2', ttlSeconds: 60 },
  { key: 'API_TOKEN', secret: 'tok', ttlSeconds: 30 },
];

function setup(onExpired = vi.fn()) {
  const view = renderHook(() => useStagedCredentials({ chatId: 'chat-1', command: 'psql -h db', onExpired }));
  return { ...view, onExpired };
}

describe('useStagedCredentials', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    client.stageOneTimeCredentials.mockReset().mockResolvedValue([
      { handleId: 'h1', key: 'DB_PASSWORD' },
      { handleId: 'h2', key: 'API_TOKEN' },
    ]);
    client.wipeOneTimeCredentials.mockReset().mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('stages for the chat and the exact command, expiring with the shortest lifetime', async () => {
    const { result } = setup();
    const startedAt = Date.now();

    await act(async () => {
      await result.current.stage(CREDENTIALS);
    });

    expect(client.stageOneTimeCredentials).toHaveBeenCalledWith('chat-1', 'psql -h db', CREDENTIALS);
    expect(result.current.staged?.items.map((item) => item.handleId)).toEqual(['h1', 'h2']);
    expect(result.current.staged?.expiresAtMs).toBe(startedAt + 30_000);
  });

  it('leaves nothing staged when the server refuses', async () => {
    client.stageOneTimeCredentials.mockRejectedValue(new Error('refused'));
    const { result } = setup();

    await act(async () => {
      await expect(result.current.stage(CREDENTIALS)).rejects.toThrow('refused');
    });

    expect(result.current.staged).toBeNull();
  });

  it('revoke destroys the staged handles on the server before forgetting them', async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.stage(CREDENTIALS);
    });

    await act(async () => {
      await result.current.revoke();
    });

    expect(client.wipeOneTimeCredentials).toHaveBeenCalledWith('chat-1', ['h1', 'h2']);
    expect(result.current.staged).toBeNull();
  });

  it('keeps the credentials when the server could not destroy them, so the caller can say so', async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.stage(CREDENTIALS);
    });
    client.wipeOneTimeCredentials.mockRejectedValue(new Error('unreachable'));

    await act(async () => {
      await expect(result.current.revoke()).rejects.toThrow('unreachable');
    });

    expect(result.current.staged).not.toBeNull();
  });

  it('discard forgets at once and still tells the server, ignoring its failure', async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.stage(CREDENTIALS);
    });
    client.wipeOneTimeCredentials.mockRejectedValue(new Error('unreachable'));

    act(() => {
      result.current.discard();
    });

    expect(result.current.staged).toBeNull();
    expect(client.wipeOneTimeCredentials).toHaveBeenCalledWith('chat-1', ['h1', 'h2']);
  });

  it('discard with nothing staged does not call the server', () => {
    const { result } = setup();

    act(() => {
      result.current.discard();
    });

    expect(client.wipeOneTimeCredentials).not.toHaveBeenCalled();
  });

  it('destroys the credentials and says so when they expire unused', async () => {
    const { result, onExpired } = setup();
    await act(async () => {
      await result.current.stage(CREDENTIALS);
    });

    await act(async () => {
      vi.advanceTimersByTime(29_999);
    });
    expect(result.current.staged).not.toBeNull();
    expect(onExpired).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(1);
    });

    expect(result.current.staged).toBeNull();
    expect(onExpired).toHaveBeenCalledTimes(1);
    expect(client.wipeOneTimeCredentials).toHaveBeenCalledWith('chat-1', ['h1', 'h2']);
  });

  it('does not announce an expiry after the credentials were revoked', async () => {
    const { result, onExpired } = setup();
    await act(async () => {
      await result.current.stage(CREDENTIALS);
    });
    await act(async () => {
      await result.current.revoke();
    });

    await act(async () => {
      vi.advanceTimersByTime(120_000);
    });

    expect(onExpired).not.toHaveBeenCalled();
  });
});
