import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ServerConnectionCloudSection from '../ServerConnectionCloudSection';

const mocks = vi.hoisted(() => ({
  openExternal: vi.fn<(url: string) => Promise<boolean>>(),
  toastError: vi.fn(),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/lib/desktopBridge', () => ({ desktopBridge: { openExternal: mocks.openExternal } }));
vi.mock('@/lib/utils/toast', () => ({ toast: { error: mocks.toastError, success: vi.fn(), info: vi.fn() } }));

const CP = 'https://cp.example.com';

async function openProviderList() {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ oauth_providers: ['google'] })));
  render(<ServerConnectionCloudSection onConnected={vi.fn()} />);
  fireEvent.change(screen.getByPlaceholderText('https://app.myrmagent.com'), { target: { value: CP } });
  fireEvent.click(screen.getByText('checkProviders'));
  return screen.findByText('continueWith');
}

describe('ServerConnectionCloudSection sign-in', () => {
  beforeEach(() => {
    localStorage.clear();
    mocks.openExternal.mockReset();
    mocks.toastError.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('opens the browser with the redirect and an S256 challenge', async () => {
    mocks.openExternal.mockResolvedValue(true);

    fireEvent.click(await openProviderList());

    await waitFor(() => expect(mocks.openExternal).toHaveBeenCalledTimes(1));
    const url = new URL(mocks.openExternal.mock.calls[0]?.[0] ?? '');
    expect(`${url.origin}${url.pathname}`).toBe(`${CP}/api/auth/oauth/google/authorize`);
    expect(url.searchParams.get('redirect')).toMatch(/^\/auth\/oauth\/callback\?desktop=1&state=[0-9a-f]{32}$/);
    expect(url.searchParams.get('code_challenge')).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(url.searchParams.get('code_challenge_method')).toBe('S256');
    expect(mocks.toastError).not.toHaveBeenCalled();
  });

  it('tells the user when the system browser could not be opened', async () => {
    mocks.openExternal.mockResolvedValue(false);

    fireEvent.click(await openProviderList());

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith('signInStartFailed'));
  });

  it('tells the user when the sign-in could not be prepared and opens nothing', async () => {
    vi.spyOn(crypto.subtle, 'digest').mockRejectedValueOnce(new Error('no subtle'));

    fireEvent.click(await openProviderList());

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith('signInStartFailed'));
    expect(mocks.openExternal).not.toHaveBeenCalled();
    expect(localStorage.getItem('myrm-cloud-oauth-pending')).toBeNull();
  });
});
