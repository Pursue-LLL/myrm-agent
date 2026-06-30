import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockSendMessage = vi.fn();
const mockEnqueue = vi.fn();
const mockToastInfo = vi.fn();

let mockLoading = false;

vi.mock('@/store/useChatStore', () => {
  const getState = () => ({
    chatId: 'test-chat-1',
    loading: mockLoading,
    sendMessage: mockSendMessage,
  });
  const store = Object.assign((selector: (s: Record<string, unknown>) => unknown) => selector(getState()), {
    getState,
  });
  return { default: store };
});

let mockDirtyArtifacts: Record<string, string> = {};
const mockClearDirtyState = vi.fn();

vi.mock('@/store/useArtifactPortalStore', () => {
  const getState = () => ({
    getDirtyArtifacts: () => mockDirtyArtifacts,
    clearDirtyState: mockClearDirtyState,
  });
  const store = Object.assign(() => ({}), { getState });
  return { default: store };
});

vi.mock('@/hooks/useMessageQueue', () => ({
  useMessageQueue: () => ({
    enqueue: mockEnqueue,
    queue: [],
    hasQueuedMessages: false,
  }),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    info: (...args: unknown[]) => mockToastInfo(...args),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { useSelectionAction } from '../useSelectionAction';

describe('useSelectionAction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLoading = false;
    mockDirtyArtifacts = {};
  });

  it('sends message via sendMessage when not loading', async () => {
    mockSendMessage.mockResolvedValue(undefined);

    const { result } = renderHook(() => useSelectionAction());

    await act(async () => {
      await result.current.sendAction({ message: 'test message' });
    });

    expect(mockSendMessage).toHaveBeenCalledWith('test message', undefined);
    expect(mockEnqueue).not.toHaveBeenCalled();
  });

  it('enqueues message when loading is true', async () => {
    mockLoading = true;

    const { result } = renderHook(() => useSelectionAction());

    await act(async () => {
      await result.current.sendAction({ message: 'queued message' });
    });

    expect(mockEnqueue).toHaveBeenCalledWith('queued message', []);
    expect(mockToastInfo).toHaveBeenCalledWith('queued');
    expect(mockSendMessage).not.toHaveBeenCalled();

    mockLoading = false;
  });

  it('injects dirty artifacts into message', async () => {
    mockDirtyArtifacts = { 'art-1': 'modified content' };
    mockSendMessage.mockResolvedValue(undefined);

    const { result } = renderHook(() => useSelectionAction());

    await act(async () => {
      await result.current.sendAction({ message: 'base message' });
    });

    const msg = mockSendMessage.mock.calls[0][0] as string;
    expect(msg).toContain('base message');
    expect(msg).toContain('<edited_artifact id="art-1">');
    expect(msg).toContain('modified content');
    expect(msg).toContain('</edited_artifact>');
    expect(mockClearDirtyState).toHaveBeenCalledWith('art-1');
  });

  it('handles multiple dirty artifacts', async () => {
    mockDirtyArtifacts = { 'a-1': 'code A', 'a-2': 'code B' };
    mockSendMessage.mockResolvedValue(undefined);

    const { result } = renderHook(() => useSelectionAction());

    await act(async () => {
      await result.current.sendAction({ message: 'msg' });
    });

    const msg = mockSendMessage.mock.calls[0][0] as string;
    expect(msg).toContain('<edited_artifact id="a-1">');
    expect(msg).toContain('<edited_artifact id="a-2">');
    expect(mockClearDirtyState).toHaveBeenCalledTimes(2);
  });

  it('calls onSent callback after sending', async () => {
    mockSendMessage.mockResolvedValue(undefined);
    const onSent = vi.fn();

    const { result } = renderHook(() => useSelectionAction({ onSent }));

    await act(async () => {
      await result.current.sendAction({ message: 'test' });
    });

    expect(onSent).toHaveBeenCalledTimes(1);
  });

  it('enqueues on AgentBusyError', async () => {
    const busyError = new Error('Agent is busy');
    busyError.name = 'AgentBusyError';
    mockSendMessage.mockRejectedValue(busyError);

    const { result } = renderHook(() => useSelectionAction());

    await act(async () => {
      await result.current.sendAction({ message: 'test' });
    });

    expect(mockEnqueue).toHaveBeenCalledTimes(1);
    expect(mockToastInfo).toHaveBeenCalledWith('queued');
  });

  it('ignores empty message', async () => {
    const { result } = renderHook(() => useSelectionAction());

    await act(async () => {
      await result.current.sendAction({ message: '' });
    });

    expect(mockSendMessage).not.toHaveBeenCalled();
    expect(mockEnqueue).not.toHaveBeenCalled();
  });

  it('exposes loading state', () => {
    mockLoading = true;

    const { result } = renderHook(() => useSelectionAction());

    expect(result.current.loading).toBe(true);

    mockLoading = false;
  });
});
