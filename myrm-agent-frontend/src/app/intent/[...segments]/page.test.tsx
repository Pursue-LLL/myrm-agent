/** @vitest-environment jsdom */
import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  push: vi.fn(),
  prefetch: vi.fn(),
  dispatch: vi.fn<(_url: string, _parsedIntent?: unknown) => Promise<boolean>>(),
  parseIntentUrl: vi.fn(),
  openFlowPad: vi.fn(),
  router: null as { replace: () => void; push: () => void; prefetch: () => void } | null,
}));

mocks.router = {
  replace: mocks.replace,
  push: mocks.push,
  prefetch: mocks.prefetch,
};

vi.mock('next/navigation', () => ({
  useRouter: () => mocks.router!,
}));

vi.mock('@/store/useFlowPadStore', () => ({
  useFlowPadStore: (selector: (state: { open: (text: string) => void }) => unknown) =>
    selector({ open: mocks.openFlowPad }),
}));

vi.mock('@/lib/intent-dispatcher', () => ({
  IntentDispatcher: class {
    dispatch = mocks.dispatch;
  },
}));

vi.mock('@/lib/intent-dispatcher/schema', () => ({
  parseIntentUrl: (...args: unknown[]) => mocks.parseIntentUrl(...args),
}));

import IntentPage from './page';

function setCurrentUrl(path: string) {
  window.history.replaceState({}, '', path);
}

describe('IntentPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.dispatch.mockResolvedValue(true);
  });

  it('dispatches ask intent once and redirects back home', async () => {
    setCurrentUrl('/intent/ask?text=hello');
    mocks.parseIntentUrl.mockReturnValue({
      scheme: 'http',
      action: 'ask',
      text: 'hello',
    });

    const { rerender } = render(<IntentPage />);
    rerender(<IntentPage />);

    await waitFor(() => {
      expect(mocks.dispatch).toHaveBeenCalledTimes(1);
    });
    expect(mocks.dispatch).toHaveBeenCalledWith(
      window.location.href,
      expect.objectContaining({ action: 'ask', text: 'hello' }),
    );
    await waitFor(() => {
      expect(mocks.replace).toHaveBeenCalledWith('/');
    });
  });

  it('redirects to home immediately when intent URL is invalid', async () => {
    setCurrentUrl('/intent/asking?text=hello');
    mocks.parseIntentUrl.mockImplementation(() => {
      throw new Error('invalid intent');
    });

    render(<IntentPage />);

    await waitFor(() => {
      expect(mocks.replace).toHaveBeenCalledWith('/');
    });
    expect(mocks.dispatch).not.toHaveBeenCalled();
  });

  it('keeps non-ask intents on current route after dispatch', async () => {
    setCurrentUrl('/intent/chat/chat-123');
    mocks.parseIntentUrl.mockReturnValue({
      scheme: 'https',
      action: 'chat',
      id: 'chat-123',
    });

    render(<IntentPage />);

    await waitFor(() => {
      expect(mocks.dispatch).toHaveBeenCalledTimes(1);
    });
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it('falls back to home when non-ask dispatch fails', async () => {
    setCurrentUrl('/intent/chat/chat-123');
    mocks.parseIntentUrl.mockReturnValue({
      scheme: 'https',
      action: 'chat',
      id: 'chat-123',
    });
    mocks.dispatch.mockResolvedValue(false);

    render(<IntentPage />);

    await waitFor(() => {
      expect(mocks.dispatch).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(mocks.replace).toHaveBeenCalledWith('/');
    });
  });
});
