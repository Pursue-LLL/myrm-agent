/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import ProviderOAuthSection from '../ProviderOAuthSection';

const stableT = (key: string, values?: Record<string, string>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const { toastSuccess, toastError } = vi.hoisted(() => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));

vi.mock('sonner', () => ({
  toast: { success: toastSuccess, error: toastError },
}));

const { apiRequest } = vi.hoisted(() => ({ apiRequest: vi.fn() }));

vi.mock('@/lib/api', () => ({ apiRequest }));

const STATUS = '/integrations/provider-oauth/status/xai';
const START = '/integrations/provider-oauth/xai/start';
const POLL = '/integrations/provider-oauth/xai/poll?user_code=ABCD-1234';
const DISCONNECT = '/integrations/provider-oauth/disconnect/xai';

const DISCONNECTED = { provider: 'xai', issuer: 'xai', connected: false };
const CONNECTED = {
  provider: 'xai',
  issuer: 'xai',
  connected: true,
  expires_at: 1893456000,
  available_models: ['grok-2', 'grok-beta'],
};
const AUTHORIZATION = {
  user_code: 'ABCD-1234',
  verification_uri: 'https://x.ai/device',
  verification_uri_complete: 'https://x.ai/device?code=ABCD-1234',
  expires_in: 600,
  interval: 5,
};

type Routes = Record<string, () => unknown>;

function serve(routes: Routes) {
  apiRequest.mockImplementation(async (path: string) => {
    const handler = routes[path];
    if (!handler) {
      throw new Error(`Unexpected request: ${path}`);
    }
    return handler();
  });
}

function requestsTo(path: string) {
  return apiRequest.mock.calls.filter(([requested]) => requested === path);
}

async function renderSection(props: Partial<React.ComponentProps<typeof ProviderOAuthSection>> = {}) {
  const onOAuthStatusChange = vi.fn();
  render(
    <ProviderOAuthSection providerId="xai" hasApiKey={false} onOAuthStatusChange={onOAuthStatusChange} {...props} />,
  );
  await act(async () => {});
  return { onOAuthStatusChange };
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function startLogin() {
  fireEvent.click(screen.getByText('loginButton'));
  await act(async () => {});
}

describe('ProviderOAuthSection', () => {
  let openSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
  });

  afterEach(() => {
    openSpy.mockRestore();
    vi.useRealTimers();
  });

  it.each(['anthropic', 'openai', 'copilot', 'custom-unknown'])('renders nothing for the %s provider', async (id) => {
    serve({});
    const { container } = render(<ProviderOAuthSection providerId={id} hasApiKey={false} />);
    await act(async () => {});

    expect(container.firstChild).toBeNull();
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('offers the SuperGrok login with its notice while not connected', async () => {
    serve({ [STATUS]: () => DISCONNECTED });
    const { onOAuthStatusChange } = await renderSection();

    expect(screen.getByText('noticeTitle')).toBeInTheDocument();
    expect(screen.getByText('noticeBody')).toBeInTheDocument();
    expect(screen.getByText('loginPrompt')).toBeInTheDocument();
    expect(screen.getByText('loginButton')).toBeInTheDocument();
    expect(screen.queryByText('connected')).not.toBeInTheDocument();
    expect(onOAuthStatusChange).toHaveBeenCalledWith(false, undefined);
  });

  it.each([
    [false, 'connectedWithQuota'],
    [true, 'connectedWithApiKey'],
  ])('shows the connection with expiry and models when connected (api key: %s)', async (hasApiKey, message) => {
    serve({ [STATUS]: () => CONNECTED });
    const { onOAuthStatusChange } = await renderSection({ hasApiKey });

    expect(screen.getByText('connected')).toBeInTheDocument();
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(screen.getByText(/^tokenExpires:/)).toBeInTheDocument();
    expect(screen.getByText('disconnect')).toBeInTheDocument();
    expect(onOAuthStatusChange).toHaveBeenCalledWith(true, ['grok-2', 'grok-beta']);
  });

  it('opens the verification page, shows the code and finishes once the authorization is approved', async () => {
    let connected = false;
    serve({
      [STATUS]: () => (connected ? CONNECTED : DISCONNECTED),
      [START]: () => AUTHORIZATION,
      [POLL]: () => {
        connected = true;
        return { status: 'success' };
      },
    });
    const { onOAuthStatusChange } = await renderSection();

    await startLogin();

    expect(requestsTo(START)[0][1]).toEqual({ method: 'POST' });
    expect(openSpy).toHaveBeenCalledWith('https://x.ai/device', '_blank', 'noopener,noreferrer');
    expect(screen.getByText('ABCD-1234')).toBeInTheDocument();
    expect(screen.getByText('waiting')).toBeInTheDocument();
    expect(requestsTo(POLL)).toHaveLength(0);

    await advance(3000);

    expect(requestsTo(POLL)[0][1]).toEqual({ method: 'POST', silent: true });
    expect(toastSuccess).toHaveBeenCalledWith('toast.connected');
    expect(onOAuthStatusChange).toHaveBeenLastCalledWith(true, ['grok-2', 'grok-beta']);
    expect(screen.getByText('connectedWithQuota')).toBeInTheDocument();
    expect(screen.queryByText('ABCD-1234')).not.toBeInTheDocument();
  });

  it('copies the device code', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    serve({ [STATUS]: () => DISCONNECTED, [START]: () => AUTHORIZATION, [POLL]: () => ({ status: 'pending' }) });
    await renderSection();
    await startLogin();

    fireEvent.click(screen.getByLabelText('copyCode'));
    await act(async () => {});

    expect(writeText).toHaveBeenCalledWith('ABCD-1234');
  });

  it('polls again after the provider asks to slow down, at twice the interval', async () => {
    serve({
      [STATUS]: () => DISCONNECTED,
      [START]: () => AUTHORIZATION,
      [POLL]: () => ({ status: 'pending', slow_down: true }),
    });
    await renderSection();
    await startLogin();

    await advance(3000);
    expect(requestsTo(POLL)).toHaveLength(1);
    await advance(5999);
    expect(requestsTo(POLL)).toHaveLength(1);
    await advance(1);
    expect(requestsTo(POLL)).toHaveLength(2);
  });

  it('keeps polling through a transient network error', async () => {
    let attempts = 0;
    serve({
      [STATUS]: () => DISCONNECTED,
      [START]: () => AUTHORIZATION,
      [POLL]: () => {
        attempts += 1;
        if (attempts === 1) {
          throw new Error('network down');
        }
        return { status: 'pending' };
      },
    });
    await renderSection();
    await startLogin();

    await advance(3000);
    await advance(3000);

    expect(requestsTo(POLL)).toHaveLength(2);
    expect(toastError).not.toHaveBeenCalled();
    expect(screen.getByText('ABCD-1234')).toBeInTheDocument();
  });

  it.each([
    ['expired', 'toast.expired'],
    ['denied', 'toast.denied'],
  ])('returns to the login prompt with a message when the authorization is %s', async (status, message) => {
    serve({ [STATUS]: () => DISCONNECTED, [START]: () => AUTHORIZATION, [POLL]: () => ({ status }) });
    await renderSection();
    await startLogin();

    await advance(3000);
    await advance(30000);

    expect(toastError).toHaveBeenCalledWith(message);
    expect(requestsTo(POLL)).toHaveLength(1);
    expect(screen.getByText('loginButton')).toBeInTheDocument();
  });

  it('gives up after ten minutes without an answer', async () => {
    serve({ [STATUS]: () => DISCONNECTED, [START]: () => AUTHORIZATION, [POLL]: () => ({ status: 'pending' }) });
    await renderSection();
    await startLogin();

    await advance(604_000);

    expect(toastError).toHaveBeenCalledWith('toast.timeout');
    expect(screen.getByText('loginButton')).toBeInTheDocument();
  });

  it('stops polling when the login is cancelled', async () => {
    serve({ [STATUS]: () => DISCONNECTED, [START]: () => AUTHORIZATION, [POLL]: () => ({ status: 'pending' }) });
    await renderSection();
    await startLogin();

    fireEvent.click(screen.getByText('cancel'));
    await advance(30000);

    expect(requestsTo(POLL)).toHaveLength(0);
    expect(screen.getByText('loginButton')).toBeInTheDocument();
  });

  it('stops polling when the section unmounts', async () => {
    serve({ [STATUS]: () => DISCONNECTED, [START]: () => AUTHORIZATION, [POLL]: () => ({ status: 'pending' }) });
    const { unmount } = render(<ProviderOAuthSection providerId="xai" hasApiKey={false} />);
    await act(async () => {});
    await startLogin();

    unmount();
    await advance(30000);

    expect(requestsTo(POLL)).toHaveLength(0);
  });

  it('reports a failed start without opening anything', async () => {
    serve({
      [STATUS]: () => DISCONNECTED,
      [START]: () => {
        throw new Error('boom');
      },
    });
    await renderSection();

    await startLogin();

    expect(toastError).toHaveBeenCalledWith('toast.startFailed');
    expect(openSpy).not.toHaveBeenCalled();
    expect(screen.getByText('loginButton')).toBeInTheDocument();
  });

  it('treats a start response without a code or page as a failed start', async () => {
    serve({ [STATUS]: () => DISCONNECTED, [START]: () => ({ interval: 5 }) });
    await renderSection();

    await startLogin();

    expect(toastError).toHaveBeenCalledWith('toast.startFailed');
    expect(openSpy).not.toHaveBeenCalled();
    await advance(30000);
    expect(requestsTo(POLL)).toHaveLength(0);
  });

  it('disconnects and tells the parent', async () => {
    serve({ [STATUS]: () => CONNECTED, [DISCONNECT]: () => undefined });
    const { onOAuthStatusChange } = await renderSection();

    fireEvent.click(screen.getByText('disconnect'));
    await act(async () => {});

    expect(requestsTo(DISCONNECT)[0][1]).toEqual({ method: 'DELETE' });
    expect(onOAuthStatusChange).toHaveBeenLastCalledWith(false);
    expect(toastSuccess).toHaveBeenCalledWith('toast.disconnected');
    expect(screen.getByText('loginButton')).toBeInTheDocument();
  });

  it('stays connected and says so when disconnecting fails', async () => {
    serve({
      [STATUS]: () => CONNECTED,
      [DISCONNECT]: () => {
        throw new Error('boom');
      },
    });
    await renderSection();

    fireEvent.click(screen.getByText('disconnect'));
    await act(async () => {});

    expect(toastError).toHaveBeenCalledWith('toast.disconnectFailed');
    expect(screen.getByText('connected')).toBeInTheDocument();
  });
});
