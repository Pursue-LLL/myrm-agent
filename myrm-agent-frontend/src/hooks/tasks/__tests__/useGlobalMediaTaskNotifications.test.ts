import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const mockNotify = vi.fn();
const mockPush = vi.fn();
const mockGetState = vi.fn(() => ({ enableWebNotifications: true }));
const mockFetchMediaTask = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, string>) => {
    if (key === 'completedTitle') return `${params?.type} completed`;
    if (key === 'failedTitle') return `${params?.type} failed`;
    if (key === 'imageGenerate') return 'Image';
    if (key === 'videoGenerate') return 'Video';
    return key;
  },
}));

vi.mock('@/store/useConfigStore', () => ({
  default: { getState: () => mockGetState() },
}));

const mockIsTauriRuntime = vi.fn(() => false);
vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return {
    ...actual,
    isTauriRuntime: () => mockIsTauriRuntime(),
  };
});

const mockSendTauriNativeNotification = vi.fn(async () => true);
const mockRequestUserAttention = vi.fn(async () => undefined);

vi.mock('@tauri-apps/api/window', () => ({
  getCurrentWindow: () => ({ requestUserAttention: (...args: unknown[]) => mockRequestUserAttention(...args) }),
}));

vi.mock('@/services/tauriNativeNotification', () => ({
  sendTauriNativeNotification: (...args: unknown[]) => mockSendTauriNativeNotification(...args),
}));

vi.mock('@/services/notification', () => ({
  notificationService: { notify: (...args: unknown[]) => mockNotify(...args) },
}));

vi.mock('@/services/mediaTasks', async () => {
  const actual = await vi.importActual<typeof import('@/services/mediaTasks')>('@/services/mediaTasks');
  return {
    ...actual,
    fetchMediaTask: (...args: unknown[]) => mockFetchMediaTask(...args),
  };
});

const listeners: Array<(event: { task_id: string; status?: string; task_type?: string }) => void> = [];

vi.mock('@/services/taskEventStream', () => ({
  subscribeTaskUpdateEvents: (listener: (event: { task_id: string; status?: string; task_type?: string }) => void) => {
    listeners.push(listener);
    return () => {
      const index = listeners.indexOf(listener);
      if (index >= 0) listeners.splice(index, 1);
    };
  },
}));

describe('useGlobalMediaTaskNotifications', () => {
  beforeEach(() => {
    listeners.length = 0;
    mockNotify.mockClear();
    mockPush.mockClear();
    mockFetchMediaTask.mockReset();
    mockSendTauriNativeNotification.mockReset();
    mockSendTauriNativeNotification.mockResolvedValue(true);
    mockRequestUserAttention.mockReset();
    mockIsTauriRuntime.mockReturnValue(false);
    mockGetState.mockReturnValue({ enableWebNotifications: true });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });
    window.history.pushState({}, '', '/');
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('notifies on terminal media task SSE update with chat deep link', async () => {
    mockFetchMediaTask.mockResolvedValue({
      task_id: 'img-1',
      task_type: 'image_generate',
      status: 'succeeded',
      payload: { prompt: 'A cat', chat_id: 'chat-99' },
      priority: 5,
      progress: 100,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:10Z',
    });

    const { useGlobalMediaTaskNotifications } = await import('../useGlobalMediaTaskNotifications');
    renderHook(() => useGlobalMediaTaskNotifications());

    await act(async () => {
      listeners[0]?.({
        task_id: 'img-1',
        status: 'succeeded',
        task_type: 'image_generate',
      });
      await Promise.resolve();
    });

    expect(mockFetchMediaTask).toHaveBeenCalledWith('img-1');
    expect(mockNotify).toHaveBeenCalledTimes(1);
    const [, options] = mockNotify.mock.calls[0] as [string, { onClick?: () => void }];
    options.onClick?.();
    expect(mockPush).toHaveBeenCalledWith('/chat/chat-99');
  });

  it('uses Tauri native notification when desktop window is hidden', async () => {
    mockIsTauriRuntime.mockReturnValue(true);
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });

    mockFetchMediaTask.mockResolvedValue({
      task_id: 'img-tauri',
      task_type: 'image_generate',
      status: 'succeeded',
      payload: { prompt: 'A cat', chat_id: 'chat-99' },
      priority: 5,
      progress: 100,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:10Z',
    });

    const { useGlobalMediaTaskNotifications } = await import('../useGlobalMediaTaskNotifications');
    renderHook(() => useGlobalMediaTaskNotifications());

    await act(async () => {
      listeners[0]?.({
        task_id: 'img-tauri',
        status: 'succeeded',
        task_type: 'image_generate',
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockSendTauriNativeNotification).toHaveBeenCalledTimes(1);
    expect(mockNotify).not.toHaveBeenCalled();
  });

  it('requests user attention when Tauri native notification is denied', async () => {
    mockIsTauriRuntime.mockReturnValue(true);
    mockSendTauriNativeNotification.mockResolvedValue(false);
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });

    mockFetchMediaTask.mockResolvedValue({
      task_id: 'img-denied',
      task_type: 'image_generate',
      status: 'succeeded',
      payload: { prompt: 'A cat', chat_id: 'chat-99' },
      priority: 5,
      progress: 100,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:10Z',
    });

    const { useGlobalMediaTaskNotifications } = await import('../useGlobalMediaTaskNotifications');
    renderHook(() => useGlobalMediaTaskNotifications());

    await act(async () => {
      listeners[0]?.({
        task_id: 'img-denied',
        status: 'succeeded',
        task_type: 'image_generate',
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockSendTauriNativeNotification).toHaveBeenCalledTimes(1);
    expect(mockRequestUserAttention).toHaveBeenCalledWith(2);
    expect(mockNotify).not.toHaveBeenCalled();
  });

  it('skips non-media SSE events without fetching task detail', async () => {
    const { useGlobalMediaTaskNotifications } = await import('../useGlobalMediaTaskNotifications');
    renderHook(() => useGlobalMediaTaskNotifications());

    await act(async () => {
      listeners[0]?.({
        task_id: 'job-1',
        status: 'succeeded',
        task_type: 'audio_transcribe',
      });
      await Promise.resolve();
    });

    expect(mockFetchMediaTask).not.toHaveBeenCalled();
    expect(mockNotify).not.toHaveBeenCalled();
  });

  it('skips notification when user is on the same visible chat page', async () => {
    window.history.pushState({}, '', '/chat/chat-99');
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });

    mockFetchMediaTask.mockResolvedValue({
      task_id: 'img-2',
      task_type: 'image_generate',
      status: 'succeeded',
      payload: { prompt: 'A dog', chat_id: 'chat-99' },
      priority: 5,
      progress: 100,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:10Z',
    });

    const { useGlobalMediaTaskNotifications } = await import('../useGlobalMediaTaskNotifications');
    renderHook(() => useGlobalMediaTaskNotifications());

    await act(async () => {
      listeners[0]?.({
        task_id: 'img-2',
        status: 'succeeded',
        task_type: 'image_generate',
      });
      await Promise.resolve();
    });

    expect(mockNotify).not.toHaveBeenCalled();
  });
});
