import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockFetchOllamaChatModel, mockEnableProviderWithModel, mockIsLocalMode } = vi.hoisted(() => ({
  mockFetchOllamaChatModel: vi.fn(),
  mockEnableProviderWithModel: vi.fn(),
  mockIsLocalMode: vi.fn(),
}));

vi.mock('@/services/ollamaChatModel', () => ({ fetchOllamaChatModel: mockFetchOllamaChatModel }));
vi.mock('@/store/config/enableProviderWithModel', () => ({ enableProviderWithModel: mockEnableProviderWithModel }));
vi.mock('@/lib/deploy-mode', () => ({ isLocalMode: mockIsLocalMode }));

import { useOllamaQuickConnect } from '../useOllamaQuickConnect';

const FOUND = { model: 'qwen3:8b', baseUrl: 'http://localhost:11434' };

describe('useOllamaQuickConnect', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsLocalMode.mockReturnValue(true);
    mockFetchOllamaChatModel.mockResolvedValue(FOUND);
  });

  it('offers the model once the server has named one', async () => {
    const { result } = renderHook(() => useOllamaQuickConnect(true));
    expect(result.current).toBeNull();

    await act(async () => {});

    expect(result.current?.model).toBe('qwen3:8b');
    expect(mockFetchOllamaChatModel).toHaveBeenCalledOnce();
  });

  it('connects the provider with the model and the address it was found at', async () => {
    mockFetchOllamaChatModel.mockResolvedValue({ model: 'qwen3:8b', baseUrl: 'http://host.docker.internal:11434' });
    const { result } = renderHook(() => useOllamaQuickConnect(true));
    await act(async () => {});

    act(() => result.current?.connect());

    expect(mockEnableProviderWithModel).toHaveBeenCalledExactlyOnceWith('ollama', 'qwen3:8b', {
      apiUrl: 'http://host.docker.internal:11434',
    });
  });

  it('does not ask while the banner is hidden', async () => {
    const { result } = renderHook(() => useOllamaQuickConnect(false));
    await act(async () => {});

    expect(mockFetchOllamaChatModel).not.toHaveBeenCalled();
    expect(result.current).toBeNull();
  });

  it('does not ask in a hosted workspace, which has no Ollama of its own', async () => {
    mockIsLocalMode.mockReturnValue(false);

    const { result } = renderHook(() => useOllamaQuickConnect(true));
    await act(async () => {});

    expect(mockFetchOllamaChatModel).not.toHaveBeenCalled();
    expect(result.current).toBeNull();
  });

  it('offers nothing when the server names no model', async () => {
    mockFetchOllamaChatModel.mockResolvedValue(null);

    const { result } = renderHook(() => useOllamaQuickConnect(true));
    await act(async () => {});

    expect(result.current).toBeNull();
  });

  it('stops offering the model when the banner hides, and asks again when it returns', async () => {
    const { result, rerender } = renderHook(({ active }) => useOllamaQuickConnect(active), {
      initialProps: { active: true },
    });
    await act(async () => {});
    expect(result.current).not.toBeNull();

    rerender({ active: false });
    expect(result.current).toBeNull();

    mockFetchOllamaChatModel.mockResolvedValue(null);
    rerender({ active: true });
    await act(async () => {});

    expect(mockFetchOllamaChatModel).toHaveBeenCalledTimes(2);
    expect(result.current).toBeNull();
  });

  it('ignores an answer that arrives after the hook unmounted', async () => {
    let answer: (value: typeof FOUND) => void = () => {};
    mockFetchOllamaChatModel.mockReturnValue(
      new Promise((resolve) => {
        answer = resolve;
      }),
    );
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { result, unmount } = renderHook(() => useOllamaQuickConnect(true));

    unmount();
    await act(async () => answer(FOUND));

    expect(result.current).toBeNull();
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});
