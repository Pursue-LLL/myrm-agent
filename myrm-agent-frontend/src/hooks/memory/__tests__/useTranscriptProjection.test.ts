import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as projectionService from '@/services/memory/transcriptProjection';
import { useTranscriptProjection } from '../useTranscriptProjection';

vi.mock('@/services/memory/transcriptProjection', () => ({
  bootstrapSessionProjection: vi.fn(),
  getSessionProjectedMessages: vi.fn(),
}));

describe('useTranscriptProjection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('initializes with default clean state', () => {
    const { result } = renderHook(() => useTranscriptProjection());

    expect(result.current.isBootstrapping).toBe(false);
    expect(result.current.isLoadingMessages).toBe(false);
    expect(result.current.lastResult).toBeNull();
    expect(result.current.messages).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('bootstraps projection and auto-loads messages on success', async () => {
    const mockBootstrapRes: projectionService.BootstrapSessionResponseDTO = {
      session_id: 'sess_1',
      bootstrapped: true,
      imported_messages: 2,
      already_bootstrapped: false,
      decisions: [
        {
          message_id: 'm1',
          transcript_entry_id: 'e1',
          status: 'adopted_unique',
          reason: 'unique content',
        },
      ],
    };
    const mockMessages: projectionService.SessionMessageDTO[] = [
      {
        message_id: 'm1',
        session_id: 'sess_1',
        seq: 1,
        role: 'user',
        content: 'hello',
        timestamp_ms: 1719662400000,
        transcript_entry_id: 'e1',
      },
    ];

    vi.mocked(projectionService.bootstrapSessionProjection).mockResolvedValueOnce(
      mockBootstrapRes
    );
    vi.mocked(projectionService.getSessionProjectedMessages).mockResolvedValueOnce(mockMessages);

    const { result } = renderHook(() => useTranscriptProjection());

    let returnedRes: projectionService.BootstrapSessionResponseDTO | null = null;
    await act(async () => {
      returnedRes = await result.current.bootstrap({
        session_id: 'sess_1',
        session_key: 'agent:main:sess_1',
      });
    });

    expect(returnedRes).toEqual(mockBootstrapRes);
    expect(result.current.lastResult).toEqual(mockBootstrapRes);
    expect(result.current.messages).toEqual(mockMessages);
    expect(result.current.isBootstrapping).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('loads projected messages directly for a session', async () => {
    const mockMessages: projectionService.SessionMessageDTO[] = [
      {
        message_id: 'm2',
        session_id: 'sess_2',
        seq: 1,
        role: 'assistant',
        content: 'ready',
        timestamp_ms: 1719662401000,
        transcript_entry_id: 'e2',
      },
    ];
    vi.mocked(projectionService.getSessionProjectedMessages).mockResolvedValueOnce(mockMessages);

    const { result } = renderHook(() => useTranscriptProjection());

    let loaded: projectionService.SessionMessageDTO[] = [];
    await act(async () => {
      loaded = await result.current.loadMessages('sess_2');
    });

    expect(loaded).toEqual(mockMessages);
    expect(result.current.messages).toEqual(mockMessages);
    expect(result.current.isLoadingMessages).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('sets error state when bootstrap fails', async () => {
    vi.mocked(projectionService.bootstrapSessionProjection).mockRejectedValueOnce(
      new Error('Network error during projection')
    );

    const { result } = renderHook(() => useTranscriptProjection());

    let returnedRes: projectionService.BootstrapSessionResponseDTO | null = null;
    await act(async () => {
      returnedRes = await result.current.bootstrap({
        session_id: 'sess_err',
        session_key: 'agent:main:sess_err',
      });
    });

    expect(returnedRes).toBeNull();
    expect(result.current.error).toBe('Network error during projection');
    expect(result.current.isBootstrapping).toBe(false);
  });

  it('resets all state to clean initial values', async () => {
    const mockMessages: projectionService.SessionMessageDTO[] = [
      {
        message_id: 'm_res',
        session_id: 'sess_res',
        seq: 1,
        role: 'user',
        content: 'temp',
      },
    ];
    vi.mocked(projectionService.getSessionProjectedMessages).mockResolvedValueOnce(mockMessages);

    const { result } = renderHook(() => useTranscriptProjection());

    await act(async () => {
      await result.current.loadMessages('sess_res');
    });
    expect(result.current.messages).toHaveLength(1);

    act(() => {
      result.current.reset();
    });

    expect(result.current.messages).toEqual([]);
    expect(result.current.lastResult).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
