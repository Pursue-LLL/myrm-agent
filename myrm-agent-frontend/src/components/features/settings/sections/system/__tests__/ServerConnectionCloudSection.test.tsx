import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ServerConnectionCloudSection from '../ServerConnectionCloudSection';

const mocks = vi.hoisted(() => ({
  openExternal: vi.fn<(url: string) => Promise<boolean>>(),
  toastError: vi.fn(),
  guardSwitch: vi.fn<(proceed: () => void) => Promise<void>>(),
  onSandboxVerified: vi.fn<(cpBase: string) => void>(),
}));

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/desktopBridge', () => ({ desktopBridge: { openExternal: mocks.openExternal } }));
vi.mock('@/lib/utils/toast', () => ({ toast: { error: mocks.toastError, success: vi.fn(), info: vi.fn() } }));

const CP = 'https://cp.example.com';

function renderSection(busy = false) {
  render(
    <ServerConnectionCloudSection
      guardSwitch={mocks.guardSwitch}
      onSandboxVerified={mocks.onSandboxVerified}
      busy={busy}
    />,
  );
  fireEvent.change(screen.getByPlaceholderText('https://app.myrmagent.com'), { target: { value: CP } });
}

async function openProviderList() {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ oauth_providers: ['google'] })));
  renderSection();
  fireEvent.click(screen.getByText('checkProviders'));
  return screen.findByText('continueWith');
}

beforeEach(() => {
  localStorage.clear();
  mocks.openExternal.mockReset();
  mocks.toastError.mockReset();
  mocks.onSandboxVerified.mockReset();
  // 默认放行：模拟没有进行中会话
  mocks.guardSwitch.mockReset().mockImplementation(async (proceed) => proceed());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ServerConnectionCloudSection sign-in', () => {
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

  it('asks for confirmation before opening the browser and starts nothing until it is given', async () => {
    mocks.openExternal.mockResolvedValue(true);
    let confirm: () => void = () => undefined;
    mocks.guardSwitch.mockImplementation(async (proceed) => {
      confirm = proceed;
    });

    fireEvent.click(await openProviderList());

    await waitFor(() => expect(mocks.guardSwitch).toHaveBeenCalledTimes(1));
    expect(mocks.openExternal).not.toHaveBeenCalled();
    expect(localStorage.getItem('myrm-cloud-oauth-pending')).toBeNull();

    confirm();
    await waitFor(() => expect(mocks.openExternal).toHaveBeenCalledTimes(1));
    expect(localStorage.getItem('myrm-cloud-oauth-pending')).not.toBeNull();
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

describe('ServerConnectionCloudSection sandbox discovery', () => {
  function stubSandboxes(response: Response | Error) {
    const spy = vi.fn(async () => {
      if (response instanceof Error) {
        throw response;
      }
      return response;
    });
    vi.stubGlobal('fetch', spy);
    return spy;
  }

  it('hands a verified cloud control plane to the parent after the confirmation', async () => {
    localStorage.setItem('auth_token', 'cp-token-abc');
    const spy = stubSandboxes(Response.json({ sandboxes: [{ id: 'sbx-1' }] }));
    renderSection();

    fireEvent.click(screen.getByText('discoverSandbox'));

    await waitFor(() => expect(mocks.onSandboxVerified).toHaveBeenCalledExactlyOnceWith(CP));
    expect(spy).toHaveBeenCalledWith(
      `${CP}/api/sandboxes`,
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer cp-token-abc' }) }),
    );
    expect(mocks.guardSwitch).toHaveBeenCalledTimes(1);
  });

  it('does not switch while the confirmation is pending or declined', async () => {
    localStorage.setItem('auth_token', 'cp-token-abc');
    stubSandboxes(Response.json({ sandboxes: [] }));
    mocks.guardSwitch.mockImplementation(async () => undefined);
    renderSection();

    fireEvent.click(screen.getByText('discoverSandbox'));

    await waitFor(() => expect(mocks.guardSwitch).toHaveBeenCalledTimes(1));
    expect(mocks.onSandboxVerified).not.toHaveBeenCalled();
  });

  it.each([
    ['no token', null, 'signInFirst'],
    ['the local placeholder token', 'local_user_token', 'signInFirst'],
  ])('asks to sign in first with %s and asks nothing else', async (_label, token, message) => {
    if (token) {
      localStorage.setItem('auth_token', token);
    }
    const spy = stubSandboxes(Response.json({}));
    renderSection();

    fireEvent.click(screen.getByText('discoverSandbox'));

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith(message));
    expect(spy).not.toHaveBeenCalled();
    expect(mocks.guardSwitch).not.toHaveBeenCalled();
    expect(mocks.onSandboxVerified).not.toHaveBeenCalled();
  });

  it.each([
    ['rejects the token', new Response('nope', { status: 401 })],
    ['is unreachable', new Error('offline')],
  ])('reports a failure and changes nothing when the control plane %s', async (_label, response) => {
    localStorage.setItem('auth_token', 'cp-token-abc');
    stubSandboxes(response);
    renderSection();

    fireEvent.click(screen.getByText('discoverSandbox'));

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith('discoverFailed'));
    expect(mocks.guardSwitch).not.toHaveBeenCalled();
    expect(mocks.onSandboxVerified).not.toHaveBeenCalled();
  });

  it('disables discovery while the parent is switching', () => {
    renderSection(true);

    expect((screen.getByText('discoverSandbox') as HTMLButtonElement).disabled).toBe(true);
  });
});
