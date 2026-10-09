/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  search: new URLSearchParams(),
  login: vi.fn<(token: string, user?: { id: string; email: string }) => Promise<void>>(),
  fetch: vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => mocks.search,
}));

vi.mock('@/store/useAuthStore', () => ({
  default: (selector: (state: { login: typeof mocks.login }) => unknown) => selector({ login: mocks.login }),
}));

vi.mock('@/lib/locale-personal-sync', () => ({ syncCookieLocaleToPersonalSettings: vi.fn(async () => undefined) }));

import OAuthCallbackPage from './page';

// 控制平面把 redirect 作为查询参数值回传，桌面标记在 redirect 内部而非顶层。
function callbackQuery(redirect: string, exchange = 'ex-1') {
  return new URLSearchParams({ exchange, redirect });
}

describe('OAuthCallbackPage', () => {
  const originalLocation = window.location;
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.login.mockResolvedValue(undefined);
    globalThis.fetch = mocks.fetch as unknown as typeof fetch;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { href: 'https://cp.example.com/auth/oauth/callback', hostname: 'cp.example.com' },
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
    globalThis.fetch = originalFetch;
  });

  it('hands the one-time exchange to the desktop app without redeeming it in the browser', async () => {
    mocks.search = callbackQuery('/auth/oauth/callback?desktop=1&state=abc123');

    render(<OAuthCallbackPage />);
    const button = await screen.findByRole('button', { name: 'openInDesktop' });
    fireEvent.click(button);

    expect(mocks.fetch).not.toHaveBeenCalled();
    expect(mocks.login).not.toHaveBeenCalled();
    expect(window.location.href).toBe('myrmagent://oauth/callback?exchange=ex-1&state=abc123');
  });

  it('keeps the browser sign-in when the redirect carries no desktop marker', async () => {
    mocks.search = callbackQuery('/chat');
    mocks.fetch.mockResolvedValue(Response.json({ token: 'tk', user_id: 'u-1', email: 'a@example.com' }));

    render(<OAuthCallbackPage />);

    await waitFor(() => expect(window.location.href).toBe('/chat'));
    expect(mocks.login).toHaveBeenCalledWith('tk', { id: 'u-1', email: 'a@example.com' });
    expect(screen.queryByRole('button', { name: 'openInDesktop' })).toBeNull();
  });

  it('ignores a desktop marker without a state', async () => {
    mocks.search = callbackQuery('/auth/oauth/callback?desktop=1');
    mocks.fetch.mockResolvedValue(Response.json({ token: 'tk', user_id: 'u-1', email: 'a@example.com' }));

    render(<OAuthCallbackPage />);

    await waitFor(() => expect(mocks.login).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: 'openInDesktop' })).toBeNull();
  });

  it('reports a missing exchange instead of rendering the desktop hand-off', async () => {
    mocks.search = new URLSearchParams({ redirect: '/auth/oauth/callback?desktop=1&state=abc123' });

    render(<OAuthCallbackPage />);

    expect(await screen.findByText('missingToken')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'openInDesktop' })).toBeNull();
  });
});
