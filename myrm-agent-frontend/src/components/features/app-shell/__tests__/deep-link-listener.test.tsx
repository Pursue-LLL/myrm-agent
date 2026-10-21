/** @vitest-environment jsdom */
import { act, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type RouterLike = {
  replace: ReturnType<typeof vi.fn>;
  push: ReturnType<typeof vi.fn>;
  prefetch: ReturnType<typeof vi.fn>;
};

const mocks = vi.hoisted(() => ({
  router: {
    replace: vi.fn(),
    push: vi.fn(),
    prefetch: vi.fn(),
  } as RouterLike,
  openFlowPad: vi.fn(),
  onOpenUrl: vi.fn(),
  unlisten: vi.fn(),
  dispatch: vi.fn<(url: string) => Promise<boolean>>(),
}));

let openUrlHandler: ((urls: string[]) => void) | null = null;

vi.mock('next/navigation', () => ({
  useRouter: () => mocks.router,
}));

vi.mock('@/store/useFlowPadStore', () => ({
  useFlowPadStore: (selector: (state: { open: (text: string) => void }) => unknown) =>
    selector({ open: mocks.openFlowPad }),
}));

vi.mock('@/lib/intent-dispatcher', () => ({
  IntentDispatcher: class {
    dispatch = (url: string) => mocks.dispatch(url);
  },
}));

vi.mock('@tauri-apps/plugin-deep-link', () => ({
  onOpenUrl: (handler: (urls: string[]) => void) => {
    openUrlHandler = handler;
    mocks.onOpenUrl(handler);
    return Promise.resolve(mocks.unlisten);
  },
}));

import DeepLinkListener from '../deep-link-listener';

async function flushQueue() {
  await Promise.resolve();
  await Promise.resolve();
}

describe('DeepLinkListener', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    openUrlHandler = null;
    mocks.dispatch.mockResolvedValue(true);
  });

  afterEach(() => {
    delete (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
  });

  it('registers deep-link listener only in tauri runtime', async () => {
    delete (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
    render(<DeepLinkListener />);
    expect(mocks.onOpenUrl).not.toHaveBeenCalled();

    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    render(<DeepLinkListener />);
    await waitFor(() => {
      expect(mocks.onOpenUrl).toHaveBeenCalledTimes(1);
    });
  });

  it('deduplicates repeated urls and dispatches sequentially', async () => {
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    let now = 1_000_000;
    const nowSpy = vi.spyOn(Date, 'now').mockImplementation(() => now);

    let resolveFirst: ((value: boolean) => void) | null = null;
    mocks.dispatch.mockImplementation((url: string) => {
      if (url === 'myrmagent://chat/1') {
        return new Promise<boolean>((resolve) => {
          resolveFirst = resolve;
        });
      }
      return Promise.resolve(true);
    });

    render(<DeepLinkListener />);
    await waitFor(() => {
      expect(mocks.onOpenUrl).toHaveBeenCalledTimes(1);
    });

    act(() => {
      openUrlHandler?.(['myrmagent://chat/1', 'myrmagent://chat/1', 'myrmagent://chat/2']);
    });
    await flushQueue();
    expect(mocks.dispatch).toHaveBeenCalledTimes(1);
    expect(mocks.dispatch).toHaveBeenNthCalledWith(1, 'myrmagent://chat/1');

    act(() => {
      resolveFirst?.(true);
    });
    await flushQueue();
    expect(mocks.dispatch).toHaveBeenCalledTimes(2);
    expect(mocks.dispatch).toHaveBeenNthCalledWith(2, 'myrmagent://chat/2');

    act(() => {
      openUrlHandler?.(['myrmagent://chat/2']);
    });
    await flushQueue();
    expect(mocks.dispatch).toHaveBeenCalledTimes(2);

    now += 3_500;
    act(() => {
      openUrlHandler?.(['myrmagent://chat/2']);
    });
    await flushQueue();
    expect(mocks.dispatch).toHaveBeenCalledTimes(3);

    nowSpy.mockRestore();
  });

  it('continues queue when one url dispatch fails and allows retry', async () => {
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    let failOnce = true;
    mocks.dispatch.mockImplementation((url: string) => {
      if (url === 'myrmagent://chat/fail' && failOnce) {
        failOnce = false;
        return Promise.reject(new Error('dispatch failed'));
      }
      return Promise.resolve(true);
    });

    render(<DeepLinkListener />);
    await waitFor(() => {
      expect(mocks.onOpenUrl).toHaveBeenCalledTimes(1);
    });

    act(() => {
      openUrlHandler?.(['myrmagent://chat/fail', 'myrmagent://chat/next']);
    });
    await flushQueue();
    await waitFor(() => {
      expect(mocks.dispatch).toHaveBeenCalledTimes(2);
    });

    expect(mocks.dispatch).toHaveBeenNthCalledWith(1, 'myrmagent://chat/fail');
    expect(mocks.dispatch).toHaveBeenNthCalledWith(2, 'myrmagent://chat/next');

    act(() => {
      openUrlHandler?.(['myrmagent://chat/fail']);
    });
    await flushQueue();

    expect(mocks.dispatch).toHaveBeenNthCalledWith(3, 'myrmagent://chat/fail');
  });

  it('unregisters tauri deep-link listener on unmount', async () => {
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    const { unmount } = render(<DeepLinkListener />);
    await waitFor(() => {
      expect(mocks.onOpenUrl).toHaveBeenCalledTimes(1);
    });
    unmount();
    expect(mocks.unlisten).toHaveBeenCalledTimes(1);
  });
});
